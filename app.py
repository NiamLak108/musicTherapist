from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from llmproxy import generate
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import logging
import re
import ast

# === ⚙️ Spotify Credentials ===
SPOTIFY_CLIENT_ID = '14745a598a994b708a8eeea02cd9cd53'
SPOTIFY_CLIENT_SECRET = '616aa8ebca9d40c6a4a1479a623c0558'
SPOTIFY_REDIRECT_URI = 'http://localhost:8888/callback'

# === 🚀 Flask App Configuration ===
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)


def create_json_response(data, status_code=200):
    response = make_response(jsonify(data), status_code)
    response.headers["Content-Type"] = "application/json"
    return response


# === 🎧 LLM QA Agent ===
def agent_playlist_QA(user_context, track_list):
    system = """
    You are an AI quality assurance agent for a music therapy playlist.
    Given user context and a track list, analyze suitability and suggest additional tracks if needed.
    Respond ONLY with `$$EXIT$$` if perfect.
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


# === 🎵 Spotify Functions ===
def search_song(mood, limit=30):
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))
    results = sp.search(q=f"{mood} music", limit=limit, type='track')
    track_uris, track_names = [], []
    for track in results.get('tracks', {}).get('items', []):
        track_info = f"{track['name']} by {track['artists'][0]['name']}"
        track_uris.append(track['uri'])
        track_names.append(track_info)
    return {"track_uris": track_uris, "track_names": track_names}


def create_playlist(user_id, playlist_name, description, track_uris):
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope='playlist-modify-public'))
    playlist = sp.user_playlist_create(user=sp.current_user()['id'], name=playlist_name, public=True,
                                       description=description)
    playlist_url = playlist['external_urls']['spotify']
    for i in range(0, len(track_uris), 100):
        sp.playlist_add_items(playlist_id=playlist['id'], items=track_uris[i:i + 100])
    return {"success": True, "url": playlist_url}


def extract_tools(text):
    matches = re.findall(r"(search_song\\s*\\(.*?\\)|create_playlist\\s*\\(.*?\\))", text, re.DOTALL)
    return matches


def execute_tool_call(tool_call, user_id, previous_output=None):
    if previous_output and "track_uris" in previous_output:
        tool_call = tool_call.replace("[track_uris]", str(previous_output["track_uris"]))
    func_name = tool_call.split("(")[0].strip()
    args_str = tool_call[len(func_name) + 1:-1]
    args = ast.literal_eval(f"[{args_str}]")
    if func_name == "create_playlist":
        return create_playlist(user_id, *args)
    elif func_name == "search_song":
        return search_song(*args, limit=30)


# === 🎙️ Rocket.Chat API Endpoint ===
@app.route('/generate_playlist', methods=['POST'])
def generate_playlist():
    try:
        user_context = request.get_json()
        user_id = user_context.get("user_id", "unknown")
        situation = user_context.get("situation", "happy")
        genre = user_context.get("genre", "pop")
        mood_preferences = user_context.get("mood_preferences", "")
        
        # 🔄 LLM for Spotify API calls
        system_prompt = f"""
        Generate Spotify API instructions:
        - Emotional state: {situation}
        - Genre: {genre}
        - Mood preferences: {mood_preferences}
        """
        response = generate(
            model='4o-mini',
            system=system_prompt,
            query=mood_preferences,
            temperature=0.5,
            lastk=10,
            session_id='MUSIC_THERAPY_AGENT',
            rag_usage=False
        )

        tool_calls = extract_tools(response.get("response", ""))
        last_output = None
        for call in tool_calls:
            last_output = execute_tool_call(call, user_id, last_output)
            if "track_names" in last_output:
                qa_feedback = agent_playlist_QA(user_context, last_output["track_names"])
                if qa_feedback.strip() != "$$EXIT$$":
                    return create_json_response({"error": "Playlist QA not approved.", "feedback": qa_feedback}, 400)

        if last_output and last_output.get("success"):
            return create_json_response({"success": True, "url": last_output.get("url")})
        else:
            return create_json_response({"error": "Playlist creation failed."}, 500)

    except Exception as e:
        logging.error(f"[ERROR] Playlist generation failed: {str(e)}")
        return create_json_response({"error": f"Playlist generation failed: {str(e)}"}, 500)


@app.route('/', methods=['GET'])
def health_check():
    return create_json_response({"text": "Rocket.Chat Music Therapy Playlist Generator is up and running!"})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

