import os
import re
import ast
import requests
import logging
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

# === ⚙️ Environment Variables for Rocket.Chat and Spotify ===
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI")
RC_TOKEN = os.environ.get("RC_token")
RC_USER_ID = os.environ.get("RC_userId")

# === 🚀 Flask App Configuration ===
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

user_sessions = {}

def create_json_response(data, status_code=200):
    response = make_response(jsonify(data), status_code)
    response.headers["Content-Type"] = "application/json"
    return response

# === 📩 Function to Send Direct Message to Rocket.Chat User ===
def send_direct_message(username, message):
    url = "https://chat.genaiconnect.net/api/v1/chat.postMessage"
    headers = {
        "Content-Type": "application/json",
        "X-Auth-Token": RC_TOKEN,
        "X-User-Id": RC_USER_ID
    }
    payload = {"channel": f"@{username}", "text": message}
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print(f"✅ Message sent to {username}: {message}")
    else:
        print(f"⚠️ Failed to send message: {response.status_code} - {response.json()}")
    return response

# === 🎧 LLM QA Agent for Playlist Suitability ===
def agent_playlist_QA(user_context, track_list):
    system = """
    You are an AI quality assurance agent for a music therapy playlist.

    Given the following:
    - The user's emotional state, age, location, and preferred music genre.
    - A list of recommended tracks (title and artist).

    Your task is to:
    - Analyze whether the playlist is contextually appropriate.
    - Suggest additional tracks (in the format: "Song - Artist") if some themes, genres, or tones are missing.
    - If the playlist is perfectly suitable, respond ONLY with the keyword `$$EXIT$$`.
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
    return response.get('response', "[DEBUG] No 'response' field in output.")

# === 🎵 Spotify Search & Playlist Functions ===
def search_song(mood, limit=30):
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))
    results = sp.search(q=f"{mood} music", limit=limit, type='track')
    track_uris, track_names = [], []
    for track in results.get('tracks', {}).get('items', []):
        track_uris.append(track['uri'])
        track_names.append(f"{track['name']} by {track['artists'][0]['name']}")
    return {"track_uris": track_uris, "track_names": track_names}

def create_spotify_playlist(user_id, playlist_name, description, track_uris):
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope='playlist-modify-public'
    ))
    playlist = sp.user_playlist_create(user=sp.current_user()['id'], name=playlist_name, public=True, description=description)
    playlist_url = playlist['external_urls']['spotify']
    for i in range(0, len(track_uris), 100):
        sp.playlist_add_items(playlist_id=playlist['id'], items=track_uris[i:i + 100])
    return {"success": True, "url": playlist_url}

# === 🤖 LLM Agent for Music Therapy ===
def agent_music_therapy(situation, age, location, genre, mood_preferences, user_id):
    system = f"""
    You are an AI music therapist. Generate Spotify API instructions based on:
    - Emotional state: {situation}
    - Age: {age}
    - Location: {location}
    - Genre: {genre}
    - Mood preferences: {mood_preferences}
    Always:
    - Retrieve 30 songs aligned with user context.
    - Call search_song and create_playlist appropriately.
    - Output code-ready instructions only (no extra text).
    """
    response = generate(
        model='4o-mini',
        system=system,
        query=mood_preferences,
        temperature=0.5,
        lastk=10,
        session_id='MUSIC_THERAPY_AGENT',
        rag_usage=False
    )
    return response.get('response', "[DEBUG] No 'response' field in output.")

# === 🔧 Execute Tool Calls ===
def execute_tool_call(tool_call, user_id, previous_output=None):
    try:
        if previous_output and "track_uris" in previous_output:
            tool_call = tool_call.replace("[track_uris]", str(previous_output["track_uris"]))
        func_name = tool_call.split("(")[0].strip()
        args_str = tool_call[len(func_name) + 1:-1]
        args = ast.literal_eval(f"[{args_str}]")
        if func_name == "create_playlist":
            return create_spotify_playlist(user_id, *args)
        elif func_name == "search_song":
            return search_song(*args, limit=30)
    except Exception as e:
        logging.error(f"[DEBUG] Error executing tool call: {str(e)}")

# === 🎙️ Unified Flask Endpoint ===
@app.route('/', methods=['POST'])
def unified_chatbot_endpoint():
    try:
        data = request.get_json()
        user_id, username = data.get("user_id", "unknown"), data.get("username", "unknown")
        user_message = data.get("text", "").strip()
        if username == "unknown":
            return create_json_response({"error": "⚠️ Username is missing."}, 400)
        session = user_sessions.get(user_id, {})
        # Dynamic flow based on session data
        if not session:
            session.update({"situation": user_message})
            send_direct_message(username, "🎂 How old are you?")
        elif "age" not in session:
            session["age"] = user_message
            send_direct_message(username, "🌍 Where are you from?:")
        elif "location" not in session:
            session["location"] = user_message
            send_direct_message(username, "🎼 Preferred music genre?:")
        elif "genre" not in session:
            session["genre"] = user_message
            send_direct_message(username, "🎵 Any specific artist or mood preferences?:")
        elif "preference" not in session:
            session["preference"] = user_message
        user_sessions[user_id] = session
        if all(k in session for k in ["situation", "age", "location", "genre", "preference"]):
            response = agent_music_therapy(
                session["situation"], session["age"], session["location"],
                session["genre"], session["preference"], user_id
            )
            tool_calls, last_output = re.findall(r"(search_song\\s*\\(.*?\\)|create_playlist\\s*\\(.*?\\))", response, re.DOTALL), None
            for call in tool_calls:
                last_output = execute_tool_call(call, user_id, last_output)
            if last_output and last_output.get("success"):
                send_direct_message(username, f"🎉 Playlist created successfully! 👉 {last_output.get('url')}")
                user_sessions.pop(user_id, None)
                return create_json_response({"text": "✅ Playlist shared successfully!"})
        return create_json_response({"text": "🤖 Awaiting next user input..."})
    except Exception as e:
        logging.error(f"[ERROR] Chatbot processing failed: {str(e)}")
        return create_json_response({"error": f"An error occurred: {str(e)}"}, 500)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)




