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


# === 🎧 LLM Agent for Music Therapy ===
def agent_music_therapy(message):
    """Handles music therapy conversation and recommends a Spotify playlist."""
    response = generate(
        model="4o-mini",
        system="""
            You are a friendly music therapist 🎶. Your job is to create the perfect playlist for the user.
            - Start with **"Feeling down? Let’s lift your mood with music! 🎵"**
            - Ask for **mood**, **music genre**, and **any favorite artists**.
            - Make it a **fun, casual conversation** with emojis.
            - Once all details are collected, **search for songs** and **create a Spotify playlist**.
            - DO NOT list what details you already have.

            🎯 Once all details are collected, generate:
            ```
            search_song('...', 30)
            create_playlist('...', '...', '...', [track_uris])
            ```
        """,
        query=f"User input: '{message}'",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy",
        rag_usage=False
    )

    response_text = response.get("response", "⚠️ Sorry, I couldn't process that. Could you rephrase?").strip()
    return response_text


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
    return jsonify({"text": "🎵 Hello from Rocket.Chat Spotify Music Therapy Bot!"})


@app.route('/query', methods=['POST'])
def handle_message():
    """Process messages from Rocket.Chat"""
    data = request.get_json()
    user = data.get("user_name", "Unknown")
    message = data.get("text", "").strip()

    print(f"[DEBUG] Incoming Message from {user}: {message}")

    if data.get("bot") or not message:
        return jsonify({"status": "ignored"})

    # Call LLM to generate structured API commands
    response = agent_music_therapy(message)
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
    app.run(host="0.0.0.0", port=5001)








