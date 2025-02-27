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

def extract_tools(text):
    print(f"[DEBUG] Extracting tools from text: {repr(text)}")
    matches = re.findall(r"(search_song\s*\(.*?\)|create_playlist\s*\(.*?\))", text, re.DOTALL)
    if matches:
        print(f"[DEBUG] Matched tool calls: {matches}")
    else:
        print("[DEBUG] No tool matched. Adjust regex or check LLM output format.")
    return matches

def search_song(mood, limit=30):
    print(f"[DEBUG] Searching songs for mood: {mood} with limit: {limit}")
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

def execute_tool_call(tool_call, user_id, previous_output=None):
    try:
        if previous_output and isinstance(previous_output, dict) and "track_uris" in previous_output:
            uris_str = str(previous_output["track_uris"])
            tool_call = tool_call.replace("[track_uris]", uris_str)
            print(f"[DEBUG] Updated tool call after replacing [track_uris]: {tool_call}")

        func_name = tool_call.split("(")[0].strip()
        args_str = tool_call[len(func_name) + 1:-1]
        args = ast.literal_eval(f"[{args_str}]")

        print(f"[DEBUG] Parsed function: {func_name} with arguments: {args}")

        if func_name == "create_playlist":
            if args[0] == user_id:
                args = args[1:]
            return create_playlist(user_id, *args)
        elif func_name == "search_song":
            return search_song(*args, limit=30)
        else:
            print(f"[DEBUG] Unknown function: {func_name}")
    except Exception as e:
        print(f"[DEBUG] Error executing tool call: {str(e)}")
        raise e

def agent_music_therapy(message, user_context):
    response = generate(
        model='4o-mini',
        system="""
        You are an AI music therapist.
        -ask the users emotional state
        -what genre they like
        - any other music preferences 
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
def hello_world():
    return jsonify({"text": 'Hello from Koyeb - you reached the main page!'})

@app.route('/query', methods=['POST'])
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


