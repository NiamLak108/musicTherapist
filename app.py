import os
import re
import ast
import requests
from flask import Flask, request, jsonify
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

app = Flask(__name__)

# === 🚀 Rocket.Chat & Spotify API Credentials ===
ROCKETCHAT_URL = os.getenv("ROCKETCHAT_URL")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

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


# === 🤖 LLM Agent for Music Therapy ===
def agent_music_therapy(situation, age, location, genre, mood_preferences, user_id):
    """Generate structured Spotify API instructions using LLM"""
    system = f"""
    You are an AI music therapist. Your task is to generate **structured** Spotify API instructions based on:
    - Emotional state: {situation}
    - Age: {age}
    - Location: {location}
    - Genre: {genre}
    - Mood preferences: {mood_preferences}

    🚀 Always return:
    1️⃣ `search_song('...', 30)`
    2️⃣ `create_playlist('{user_id}', '...', '...', [track_uris])`

    ❌ DO NOT return any explanations, comments, or extra text.

    🔹 Example Response:
    ```
    search_song('sad pop for someone feeling down in London', 30)
    create_playlist('{user_id}', 'Sad Pop Playlist', 'A playlist for those who enjoy sad pop music', [track_uris])
    ```
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


def extract_tools(text):
    """Extract search_song and create_playlist function calls from LLM response"""
    print(f"[DEBUG] Raw LLM Response: {repr(text)}")  
    matches = re.findall(r"(search_song\s*\(.*?\)|create_playlist\s*\(.*?\))", text, re.MULTILINE | re.IGNORECASE)

    if matches:
        print(f"[DEBUG] Matched tool calls: {matches}")
    else:
        print("[DEBUG] No tool matched. Adjust regex or check LLM output format.")
    
    return matches


# === 🚀 Flask Endpoints ===
@app.route('/', methods=['POST'])
def home():
    """Default route for verification"""
    return jsonify({"text": "Hello from Rocket.Chat Spotify Bot!"})


@app.route('/query', methods=['POST'])
def handle_message():
    """Process messages from Rocket.Chat"""
    data = request.get_json()

    user = data.get("user_name", "Unknown")
    message = data.get("text", "")

    print(f"[DEBUG] Incoming Message from {user}: {message}")

    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})

    # Extract user context
    user_context = {
        "user_id": user,
        "situation": message,  # Assume message contains emotional state
        "age": "25",  # Default for now (Can be improved with NLP)
        "location": "London",  # Default for now
        "genre": "pop",  # Default for now
        "mood_preferences": message
    }

    response = agent_music_therapy(
        user_context["situation"], user_context["age"], user_context["location"],
        user_context["genre"], user_context["mood_preferences"], user_context["user_id"]
    )

    tool_calls = extract_tools(response)
    last_output = None

    for call in tool_calls:
        if "create_playlist" in call and last_output and "track_uris" in last_output:
            call = call.replace("[track_uris]", str(last_output["track_uris"]))
            print(f"[DEBUG] Updated tool call: {call}")

        try:
            last_output = eval(call)  # Execute tool call dynamically
        except Exception as e:
            return jsonify({"text": f"❌ Error executing command: {str(e)}"})

    if last_output and last_output.get("success"):
        return jsonify({"text": f"🎵 Playlist created! 👉 {last_output.get('url')}"})
    else:
        return jsonify({"text": "⚠️ Playlist creation failed. Try again later."})


@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    return "Not Found", 404


# === 🚀 Run Flask App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)








