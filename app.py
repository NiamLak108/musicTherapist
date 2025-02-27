import os
import re
import ast
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

app = Flask(__name__)

# Load environment variables
load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

# Initialize Spotify client
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

def search_song(mood, genre, limit=30):
    """Searches for songs based on mood and genre."""
    print(f"[DEBUG] Searching songs for mood: {mood}, genre: {genre}, limit: {limit}")
    results = sp.search(q=f"{mood} {genre} music", limit=limit, type='track')
    track_uris = [track['uri'] for track in results.get('tracks', {}).get('items', [])]
    track_names = [f"{track['name']} by {track['artists'][0]['name']}" for track in results.get('tracks', {}).get('items', [])]
    
    return {"track_uris": track_uris, "track_names": track_names}

def create_playlist(user_id, playlist_name, description, track_uris):
    """Creates a playlist on Spotify and adds tracks to it."""
    sp_oauth = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope='playlist-modify-public'
    ))
    
    current_user_id = sp_oauth.current_user()['id']
    playlist = sp_oauth.user_playlist_create(user=current_user_id, name=playlist_name, public=True, description=description)
    playlist_url = playlist['external_urls']['spotify']
    sp_oauth.playlist_add_items(playlist_id=playlist['id'], items=track_uris)
    
    return {"success": True, "url": playlist_url}

@app.route('/', methods=['POST'])
def main():
    data = request.get_json()
    print(f"[DEBUG] Received request: {data}")

    user = data.get("user_name", "Unknown")
    message = data.get("text", "").strip().lower()

    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})

    print(f"[DEBUG] Message from {user}: {message}")

    # Retrieve or initialize user context
    user_context = data.get("user_context", {})

    # **Step 1: Ask about Mood (Difficult Time)**
    if "mood" not in user_context:
        user_context["mood"] = message
        return jsonify({
            "text": "🎂 How old are you?",
            "user_context": user_context
        })

    # **Step 2: Ask Age**
    if "age" not in user_context:
        user_context["age"] = message
        return jsonify({
            "text": "🌍 Where are you from?",
            "user_context": user_context
        })

    # **Step 3: Ask Location**
    if "location" not in user_context:
        user_context["location"] = message
        return jsonify({
            "text": "🎼 What’s your favorite music genre? (e.g., pop, rock, jazz, classical)",
            "user_context": user_context
        })

    # **Step 4: Ask Music Genre**
    if "genre" not in user_context:
        user_context["genre"] = message
        return jsonify({
            "text": "🎵 Any additional music preferences? (e.g., instrumental, slow songs, upbeat, no)",
            "user_context": user_context
        })

    # **Step 5: Capture Additional Preferences**
    if "preferences" not in user_context:
        user_context["preferences"] = message
        return jsonify({
            "text": "✨ Perfect! I'm creating your playlist now...",
            "user_context": user_context
        })

    # **Step 6: Generate Playlist**
    mood = user_context.get("mood")
    genre = user_context.get("genre")

    if mood and genre:
        search_results = search_song(mood, genre)
        if not search_results["track_uris"]:
            return jsonify({"text": "I couldn't find any songs matching your mood and genre. Try again with different keywords!"})

        playlist_response = create_playlist(user, f"{mood.capitalize()} {genre.capitalize()} Playlist", f"A playlist for your {mood} mood.", search_results["track_uris"])
        
        if playlist_response["success"]:
            return jsonify({
                "text": f"🎉 Playlist created successfully! 👉 {playlist_response['url']}",
                "user_context": {}  # Clear context after successful playlist creation
            })

    return jsonify({"text": "Something went wrong. Please try again."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)








