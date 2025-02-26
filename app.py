import os
import requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import logging
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
        welcome_message = "💬 Tell me how you're feeling or what you would like to listen to today:"
        send_direct_message(username, welcome_message)
        return create_json_response({"text": "✅ Initial message sent successfully!"})
    else:
        return create_json_response({"error": "⚠️ Username is missing."}, 400)

# === 🎙️ Progressive Chatbot Interaction Endpoint (Dynamic Input Handling) ===
@app.route('/', methods=['POST'])
def chatbot_interaction():
    try:
        data = request.get_json()
        user_id = data.get("user_id", "unknown")
        username = data.get("username", "unknown")
        user_message = data.get("text", "").strip()
        session = user_sessions.get(user_id, {})

        # Dynamically store any user input
        if "situation" not in session:
            session["situation"] = user_message
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

        # Generate playlist after all inputs
        if all(field in session for field in ["situation", "age", "location", "genre", "preference"]):
            playlist_name = "Music Therapy Playlist"
            description = (
                f"Mood: {session['situation']}, Age: {session['age']}, Location: {session['location']}, "
                f"Genre: {session['genre']}, Preferences: {session['preference']}"
            )
            playlist_result = create_spotify_playlist(user_id, playlist_name, description, [])

            if playlist_result["success"]:
                send_direct_message(
                    username,
                    f"🎉 Playlist created successfully! 👉 Access here: {playlist_result['url']}"
                )
                user_sessions.pop(user_id, None)
                return create_json_response({"text": "✅ Playlist shared successfully!"})
            else:
                return create_json_response({"text": "⚠️ Failed to create playlist."})

        return create_json_response({"text": "🤖 Awaiting next user input..."})

    except Exception as e:
        logging.error(f"[ERROR] Chatbot processing failed: {str(e)}")
        return create_json_response({"error": f"An error occurred: {str(e)}"}, 500)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)





