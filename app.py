import os
import re
import ast
import requests
from flask import Flask, request, jsonify
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from dotenv import load_dotenv

app = Flask(__name__)

# === 🛠 Load API Keys & Environment Variables ===
load_dotenv()
ROCKETCHAT_URL = os.getenv("ROCKETCHAT_URL")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

# === 💾 Session Storage for Users (Tracks Conversation State) ===
user_sessions = {}  # Stores user conversation progress

def get_or_create_session(user_id):
    """Retrieves or initializes a session for a user."""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "step": "waiting_for_trigger",  # Waits for user to say "I need a playlist"
            "mood": None,
            "age": None,
            "genre": None,
            "artist": None
        }
    return user_sessions[user_id]


# === 🎵 Spotify Functions ===
def search_song(mood, limit=30):
    """Search for songs based on mood"""
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))

    results = sp.search(q=f"{mood} music", limit=limit, type='track')
    track_uris = []
    track_names = []

    items = results.get('tracks', {}).get('items', [])
    if not items:
        return {"summary": "No tracks found.", "track_uris": [], "track_names": []}

    for track in items:
        track_info = f"{track['name']} by {track['artists'][0]['name']}"
        track_uris.append(track['uri'])
        track_names.append(track_info)

    return {"summary": "Here are some recommended songs.", "track_uris": track_uris, "track_names": track_names}


def create_playlist(user_id, playlist_name, description, track_uris):
    """Create a Spotify playlist and add songs"""
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope='playlist-modify-public'
    ))

    try:
        current_user_id = sp.current_user()['id']
        playlist = sp.user_playlist_create(user=current_user_id, name=playlist_name, public=True, description=description)
        playlist_url = playlist['external_urls']['spotify']

        for i in range(0, len(track_uris), 100):
            sp.playlist_add_items(playlist_id=playlist['id'], items=track_uris[i:i+100])

        return {"success": True, "url": playlist_url}

    except Exception as e:
        return {"success": False, "message": str(e)}


# === 🚀 Flask Endpoints ===
@app.route('/', methods=['POST'])
def home():
    """Default route for verification"""
    return jsonify({"text": "🎵 Hello from Rocket.Chat Spotify Music Therapy Bot!"})


@app.route('/query', methods=['POST'])
def handle_message():
    """Process messages from Rocket.Chat"""
    data = request.get_json()
    user_id = data.get("user_name", "Unknown")
    message = data.get("text", "").strip().lower()

    print(f"[DEBUG] Incoming Message from {user_id}: {message}")

    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})

    session = get_or_create_session(user_id)  # Retrieve user session

    # === 🚀 Start Conversation if Triggered ===
    if "playlist" in message and session["step"] == "waiting_for_trigger":
        session["step"] = "ask_mood"
        return jsonify({"text": "🎶 What mood are you in? (e.g., happy, sad, energetic) 🎵"})

    # === 📜 Conversation Flow ===
    if session["step"] == "ask_mood":
        session["mood"] = message
        session["step"] = "ask_age"
        return jsonify({"text": "🎂 How old are you?"})

    elif session["step"] == "ask_age":
        if not message.isdigit():
            return jsonify({"text": "🎂 Please enter a valid age (e.g., 25)."})
        session["age"] = int(message)
        session["step"] = "ask_genre"
        return jsonify({"text": "🎶 What’s your favorite music genre?"})

    elif session["step"] == "ask_genre":
        session["genre"] = message
        session["step"] = "ask_artist"
        return jsonify({"text": "🎤 Do you have a favorite artist?"})

    elif session["step"] == "ask_artist":
        session["artist"] = message
        session["step"] = "creating_playlist"

        # 🎵 Generate Playlist Request
        response = generate(
            model="4o-mini",
            system=f"""
                You are an AI music therapist. Based on the user’s emotional state, age, and music preferences,
                create a personalized **Spotify playlist**.

                - Mood: {session['mood']}
                - Age: {session['age']}
                - Genre: {session['genre']}
                - Favorite Artist: {session['artist']}

                🎯 Generate:
                ```
                search_song('...', 30)
                create_playlist('...', '...', '...', [track_uris])
                ```
            """,
            query="Generate playlist",
            temperature=0.5,
            lastk=10,
            session_id=f"music-therapy-{user_id}",
            rag_usage=False
        )

        tool_calls = extract_tools(response.get("response", ""))
        last_output = None

        for call in tool_calls:
            if "create_playlist" in call and last_output and "track_uris" in last_output:
                call = call.replace("[track_uris]", str(last_output["track_uris"]))
                print(f"[DEBUG] Updated tool call: {call}")

            try:
                last_output = eval(call)  # Execute tool call dynamically
            except Exception as e:
                return jsonify({"text": f"❌ Error: {str(e)}"})

        if last_output and last_output.get("success"):
            return jsonify({"text": f"🎵 Playlist created! 👉 {last_output.get('url')}"})
        else:
            return jsonify({"text": "⚠️ Playlist creation failed. Try again later."})

    return jsonify({"text": "❌ Unexpected error occurred."})


@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    return "Not Found", 404


def extract_tools(text):
    """Extract search_song and create_playlist function calls from LLM response"""
    print(f"[DEBUG] Raw LLM Response: {repr(text)}")  
    matches = re.findall(r"(search_song\s*\(.*?\)|create_playlist\s*\(.*?\))", text, re.MULTILINE | re.IGNORECASE)
    return matches if matches else []


# === 🚀 Run Flask App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)










