import os
import requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import logging
import re
import ast

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

# === 🎵 Create Spotify Playlist ===
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

# === 🎙️ Flask Endpoint to Initiate Conversation ===
@app.route('/start', methods=['POST'])
def start_conversation():
    data = request.get_json()
    username = data.get("username", "unknown")
    if username != "unknown":
        welcome_message = "👋 Hi there! I'm your music therapy assistant. How are you feeling today emotionally?"
        send_direct_message(username, welcome_message)
        return create_json_response({"text": "✅ Initial message sent successfully!"})
    else:
        return create_json_response({"error": "⚠️ Username is missing."}, 400)

# === 🎙️ Progressive Chatbot Interaction Endpoint ===
@app.route('/', methods=['POST'])
def chatbot_interaction():
    try:
        data = request.get_json()
        user_id = data.get("user_id", "unknown")
        username = data.get("username", "unknown")
        user_message = data.get("text", "").lower()
        session = user_sessions.get(user_id, {"last_question": None})

        mood_match = re.search(r"(?i)(sad|happy|angry|excited|heartbroken|anxious)", user_message)
        genre_match = re.search(r"(?i)(pop|rock|jazz|classical|hip hop|rnb|country)", user_message)
        age_match = re.search(r"(?i)(\\d{1,2})", user_message)
        location_match = re.search(r"(?i)(?:in|from)\\s+(\\w+)", user_message)

        if mood_match and "situation" not in session:
            session["situation"] = mood_match.group(0)
        if age_match and "age" not in session:
            session["age"] = age_match.group(0)
        if location_match and "location" not in session:
            session["location"] = location_match.group(1)
        if genre_match and "genre" not in session:
            session["genre"] = genre_match.group(0)

        user_sessions[user_id] = session

        required_fields = ["situation", "genre", "age", "location"]
        missing_fields = [field for field in required_fields if field not in session]

        questions = {
            "situation": "💬 How are you feeling emotionally right now?",
            "genre": "🎵 What's your favorite music genre?",
            "age": "🎂 How old are you?",
            "location": "🌍 Where are you from?"
        }

        if missing_fields:
            for field in missing_fields:
                if session.get("last_question") != field:
                    session["last_question"] = field
                    user_sessions[user_id] = session
                    send_direct_message(username, questions[field])
                    return create_json_response({"text": f"🤖 Asked {field} question."})

        playlist_result = create_spotify_playlist(user_id, "Music Therapy Playlist", "Personalized music therapy playlist", [])

        if playlist_result["success"]:
            send_direct_message(username, f"🎉 Your personalized playlist is ready: {playlist_result['url']}")
            user_sessions.pop(user_id, None)
            return create_json_response({"text": "✅ Playlist shared successfully!"})
        else:
            return create_json_response({"text": "⚠️ Failed to create playlist."})

    except Exception as e:
        logging.error(f"[ERROR] Chatbot processing failed: {str(e)}")
        return create_json_response({"error": f"An error occurred: {str(e)}"}, 500)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)




