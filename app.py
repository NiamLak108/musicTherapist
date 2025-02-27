import os
import requests
from flask import Flask, request, jsonify
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from dotenv import load_dotenv

app = Flask(__name__)

# === 🛠 Load API Keys & Environment Variables ===
load_dotenv()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

# === 🎵 Spotify Functions ===
def search_song(mood, limit=30):
    """Search for songs based on user mood"""
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))

        results = sp.search(q=f"{mood} music", limit=limit, type='track')
        track_uris = [track['uri'] for track in results.get('tracks', {}).get('items', [])]

        return track_uris if track_uris else None
    except Exception as e:
        print(f"[ERROR] search_song failed: {e}")
        return None

def create_playlist(user_id, playlist_name, description, track_uris):
    """Create a Spotify playlist and add songs"""
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope='playlist-modify-public'
        ))

        current_user_id = sp.current_user()['id']
        playlist = sp.user_playlist_create(user=current_user_id, name=playlist_name, public=True, description=description)
        sp.playlist_add_items(playlist_id=playlist['id'], items=track_uris)

        return playlist['external_urls']['spotify']
    except Exception as e:
        print(f"[ERROR] create_playlist failed: {e}")
        return None

# === 🚀 Flask Endpoints ===
@app.route('/query', methods=['POST'])
def handle_message():
    """Handles messages from Rocket.Chat, asks for mood, and generates a playlist"""
    data = request.get_json()
    user_id = data.get("user_name", "Unknown")
    message = data.get("text", "").strip().lower()

    print(f"[DEBUG] Received from {user_id}: {message}")

    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})

    # 🚀 If user is saying "hello" or something general, introduce the bot
    if "hello" in message or "hi" in message or "what can you do" in message:
        return jsonify({"text": "🎵 **Welcome! I'm a Music Therapy Bot.**\n\nTell me how you're feeling, and I'll create a **Spotify playlist** just for you! 🧘‍♂️🎶\n\nFor example, say:\n- 'I'm feeling stressed'\n- 'I need focus music'\n- 'Make me a happy playlist' 🎧"})

    # 🎵 Call LLM to determine the playlist theme
    response = generate(
        model="4o-mini",
        system="You are a music assistant. Generate a playlist theme based on the user's mood or request.",
        query=message,
        temperature=0.5,
        lastk=10,
        session_id=f"music-therapy-{user_id}",
        rag_usage=False
    )

    playlist_theme = response.get("response", "").strip()
    if not playlist_theme:
        return jsonify({"text": "⚠️ I couldn't determine a playlist theme. Try again!"})

    # 🎶 Fetch songs
    track_uris = search_song(playlist_theme)
    if not track_uris:
        return jsonify({"text": "⚠️ No songs found for that theme. Try another mood!"})

    # 🎼 Create playlist
    playlist_url = create_playlist(user_id, f"{playlist_theme} Playlist", "A playlist based on your mood.", track_uris)
    if not playlist_url:
        return jsonify({"text": "⚠️ Failed to create playlist. Please try again later."})

    return jsonify({"text": f"🎵 Here's your **{playlist_theme} Playlist**: {playlist_url}"})

# === 🚀 Run Flask App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)










