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

def agent_playlist_QA(user_context, track_list):
    system = """
    You are an AI quality assurance agent for a music therapy playlist.
    Analyze whether the playlist suits the user's emotional needs.
    Suggest missing tracks if needed, or return `$$EXIT$$` if perfect.
    """

    track_summary = "\n".join([f"- {track}" for track in track_list])
    query = f"""
    User context:
    - Emotional state: {user_context['situation']}
    - Age: {user_context['age']}
    - Location: {user_context['location']}
    - Preferred genre: {user_context['genre']}
    
    Playlist tracks:
    {track_summary}
    """

    response = generate(
        model='4o-mini',
        system=system,
        query=query,
        temperature=0.3,
        lastk=10,
        session_id='MUSIC_THERAPY_QA',
        rag_usage=False
    )

    return response.get('response', 'Error in QA agent')

def search_song(mood, limit=30):
    results = sp.search(q=f"{mood} music", limit=limit, type='track')
    track_uris = [track['uri'] for track in results.get('tracks', {}).get('items', [])]
    track_names = [f"{track['name']} by {track['artists'][0]['name']}" for track in results.get('tracks', {}).get('items', [])]
    
    return {"track_uris": track_uris, "track_names": track_names}

def create_playlist(user_id, playlist_name, description, track_uris):
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

def agent_music_therapy(message, user_context):
    response = generate(
        model='4o-mini',
        system="""
        You are an AI music therapist.
        Given the user's emotional state, genre, and mood preferences, generate a Spotify playlist.
        Use search_song() to retrieve songs and create_playlist() to generate a playlist.
        """,
        query=message,
        temperature=0.5,
        lastk=10,
        session_id='MUSIC_THERAPY_AGENT',
        rag_usage=False
    )
    return response.get('response', 'Error in therapy agent')



@app.route('/', methods=['POST'])
def main():
    data = request.get_json()
    print(f"Received request: {data}")  # Debugging print statement
    
    user = data.get("user_name", "Unknown")
    message = data.get("text", "")
    
    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})
    
    print(f"Message from {user}: {message}")
    
    user_context = data.get("user_context", {})
    response_text = agent_music_therapy(message, user_context)
    
    tool_calls = extract_tools(response_text)
    last_output = None
    
    for call in tool_calls:
        print(f"[DEBUG] 🚀 Executing tool call: {call}")
        last_output = execute_tool_call(call, user, last_output)
    
    if last_output and isinstance(last_output, dict) and last_output.get("success"):
        return jsonify({"text": f"Playlist created successfully! Access it here: {last_output.get('url')}"})
    
    return jsonify({"text": "Something went wrong. Please try again."})

@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)


