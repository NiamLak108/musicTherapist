import os
from flask import Flask, request, jsonify
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)

# === 🎵 Hardcoded Spotify Credentials ===
SPOTIFY_CLIENT_ID = '14745a598a994b708a8eeea02cd9cd53'
SPOTIFY_CLIENT_SECRET = '616aa8ebca9d40c6a4a1479a623c0558'
SPOTIFY_REDIRECT_URI = 'http://localhost:8888/callback'

# **Pre-generated tokens (Replace these with actual values)**
ACCESS_TOKEN = "BQCmVHfXFOr1FpIsD0Rf4PWupKwkf_-fA50OTDnyFI5N0ree-kX1Z3MHJ38_uWrSNsXlEtNAxR6ZJqdOwAkeze0-K2u3mBlVVKKvi3fWRgdkRFuNCe6tsoomnoFEfda5F7yjfLFsQWlAX7vcOv_IK557a9ld0-MNJSAUCZA-rf--2_34F3iXioWtDZUTxE_NWaIfJ7dheTGm4swvK0jtfTmRn4dYBPpnIgn1Di9tY5PA"
REFRESH_TOKEN = "AQCtcTcd2HdE1SXfXHlzXkiMPme6kiSkywiTka1aDFK-W9MSsCCzc08-IBE2me6zfcFlovwfgDBhLu1g5nkziyTCn1U65PwhhNUDPKj7Bys5JOBGGlhIWX6ZVAWuVaSPGco"

# **Explicitly setting the Spotify user ID to "helloniam"**
SPOTIFY_USER_ID = "helloniam"

# === 🎵 Spotify Authentication ===
sp = spotipy.Spotify(auth=ACCESS_TOKEN)


def refresh_spotify_token():
    """Refreshes the Spotify access token if it expires."""
    try:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="playlist-modify-public"
        )
        new_token_info = auth_manager.refresh_access_token(REFRESH_TOKEN)
        print("[DEBUG] Refreshed Spotify token.")
        return new_token_info["access_token"]
    except Exception as e:
        print(f"[ERROR] Failed to refresh Spotify token: {e}")
        return None


def extract_songs(playlist_text):
    """Extracts song titles and artists from the LLM-generated playlist."""
    songs = []
    lines = playlist_text.split("\n")
    for line in lines:
        if line.strip() and line[0].isdigit():
            parts = line.split(" - ")
            if len(parts) == 2:
                song_title = parts[0].split(". ")[1].strip()
                artist = parts[1].strip()
                songs.append((song_title, artist))
    print(f"[DEBUG] Extracted Songs: {songs}")  # Debugging log
    return songs


def search_songs(songs):
    """Searches Spotify for song URIs using the stored token."""
    track_uris = []
    global sp
    sp = spotipy.Spotify(auth=refresh_spotify_token())

    for song, artist in songs:
        try:
            results = sp.search(q=f"track:{song} artist:{artist}", limit=1, type="track")
            tracks = results.get("tracks", {}).get("items", [])
            if tracks:
                track_uris.append(tracks[0]["uri"])
        except Exception as e:
            print(f"[ERROR] Failed to search for {song} by {artist}: {e}")
    
    print(f"[DEBUG] Found Track URIs: {track_uris}")  # Debugging log
    return track_uris


def create_spotify_playlist(playlist_name, track_uris):
    """Creates a Spotify playlist for 'helloniam' and adds songs."""
    global sp
    sp = spotipy.Spotify(auth=refresh_spotify_token())

    # **Truncate playlist name to 100 characters**
    if len(playlist_name) > 100:
        playlist_name = playlist_name[:97] + "..."

    try:
        print(f"[DEBUG] Creating Playlist: {playlist_name}")  # Debugging log

        playlist = sp.user_playlist_create(
            user=SPOTIFY_USER_ID,
            name=playlist_name,
            public=True,
            description="A custom playlist generated by Melody 🎶"
        )

        if track_uris:
            sp.playlist_add_items(playlist_id=playlist["id"], items=track_uris)

        print(f"[DEBUG] Playlist Created Successfully: {playlist['external_urls']['spotify']}")  # Debugging log
        return playlist["external_urls"]["spotify"]

    except spotipy.exceptions.SpotifyException as e:
        print(f"[ERROR] Spotify API Error: {e.http_status} - {e.msg}")  # Detailed Spotify error
        return None

    except Exception as e:
        print(f"[ERROR] Unexpected Error During Playlist Creation: {e}")
        return None


def generate_playlist(mood, genre):
    """Uses LLM to generate a playlist."""
    response = generate(
        model="4o-mini",
        system="""
            You are a **music therapy assistant** named MELODY 🎶. Your job is to create **safe, fun, and engaging playlists** for users.
            - Generate a **10-song playlist** based on the user's mood & genre.
            - Format the response as:
              "**🎵 Playlist: [Creative Playlist Name]**\n
              1. [Song 1] - [Artist]\n
              2. [Song 2] - [Artist]\n
              ...
              10. [Song 10] - [Artist]"
        """,
        query=f"Mood: {mood}, Genre: {genre}",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )

    playlist_text = response.get("response", "").strip()
    
    print(f"[DEBUG] LLM Playlist Response:\n{playlist_text}")  # Debugging log

    if not playlist_text:
        return None, "⚠️ Sorry, I couldn't generate a playlist. Try again!"
    
    return playlist_text, extract_songs(playlist_text)


def music_assistant_llm(message):
    """Handles user input and generates a playlist."""
    response = generate(
        model="4o-mini",
        system="""
            You are a **music therapy assistant** named MELODY 🎶. 
            - If the user hasn't provided both **mood** and **genre**, ask for them.
            - Once both are provided, confirm and generate a playlist.
            - Format the response as:  
              "Mood: [mood]\nGenre: [genre]"
        """,
        query=f"User input: '{message}'\nCurrent preferences: {{'mood': None, 'genre': None}}",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )

    response_text = response.get("response", "").strip()
    print(f"[DEBUG] LLM Mood & Genre Response: {response_text}")  # Debugging log

    mood, genre = None, None
    if "mood:" in response_text.lower() and "genre:" in response_text.lower():
        try:
            mood = response_text.split("Mood:")[1].split("Genre:")[0].strip()
            genre = response_text.split("Genre:")[1].strip()
        except IndexError:
            return "⚠️ I couldn't determine both mood and genre. Try again!"

    if not mood or not genre:
        return response_text  

    # Generate Playlist
    playlist_text, songs = generate_playlist(mood, genre)
    if not playlist_text:
        return "⚠️ Couldn't generate a playlist. Try again!"

    # Search and create Spotify playlist
    track_uris = search_songs(songs)
    spotify_url = create_spotify_playlist(f"{mood} {genre} Playlist", track_uris)

    return f"{playlist_text}\n\n🎶 **Listen on Spotify:** {spotify_url}" if spotify_url else f"{playlist_text}\n\n⚠️ Couldn't create a Spotify playlist, but here are the songs!"


@app.route('/', methods=['POST'])
def main():
    data = request.get_json()
    message = data.get("text", "").strip()

    return jsonify({"text": music_assistant_llm(message)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)




















