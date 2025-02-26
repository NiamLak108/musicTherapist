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

user_sessions = {}

def create_json_response(data, status_code=200):
    if "response" in data:
        data["text"] = data.pop("response")
    response = make_response(jsonify(data), status_code)
    response.headers["Content-Type"] = "application/json"
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
    - Suggest additional tracks if necessary in the format "Song - Artist".
    - If perfect, respond ONLY with `$$EXIT$$`.
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
        session_id=f"MUSIC_THERAPY_QA_{user_context['user_id']}",
        rag_usage=False
    )
    return response.get('response', "[DEBUG] No 'response' field in output.")

# === 🎙️ Progressive Chatbot Interaction with Enhanced State Validation ===
@app.route('/', methods=['POST'])
def chatbot_interaction():
    try:
        data = request.get_json()
        user_id = data.get("user_id", "unknown")
        user_message = data.get("text", "").lower()
        session = user_sessions.get(user_id, {"last_question": None})

        # Extract multiple details from a single message using regex
        mood_match = re.search(r"(?i)(sad|happy|angry|excited|heartbroken|anxious)", user_message)
        age_match = re.search(r"(?i)(\\d{1,2})", user_message)
        location_match = re.search(r"(?i)(?:in|from)\\s+(\\w+)", user_message)
        genre_match = re.search(r"(?i)(pop|rock|jazz|classical|hip hop|rnb|country)", user_message)

        if mood_match and "situation" not in session:
            session["situation"] = mood_match.group(0)
        if age_match and "age" not in session:
            session["age"] = age_match.group(0)
        if location_match and "location" not in session:
            session["location"] = location_match.group(1)
        if genre_match and "genre" not in session:
            session["genre"] = genre_match.group(0)

        user_sessions[user_id] = session

        # State validation with memory of the last asked question
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
                    return create_json_response({"text": questions[field]})

        # If all details are present, proceed directly to playlist generation
        response = agent_music_therapy(
            session["situation"], session["age"], session["location"],
            session["genre"], "", user_id
        )

        tool_calls = extract_tools(response)
        last_output = None

        for call in tool_calls:
            last_output = execute_tool_call(call, user_id, last_output)

        if last_output and last_output.get("success"):
            user_sessions.pop(user_id, None)
            return create_json_response({"text": f"🎉 Playlist created successfully! Access it here: {last_output.get('url')}"})
        else:
            return create_json_response({"text": "⚠️ Something went wrong while creating your playlist. Please try again!"})

    except Exception as e:
        logging.error(f"[ERROR] Chatbot processing failed: {str(e)}")
        return create_json_response({"error": f"An error occurred: {str(e)}"}, 500)

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
        session_id=f"MUSIC_THERAPY_AGENT_{user_id}",
        rag_usage=False
    )
    return response.get('response', "[DEBUG] No 'response' field in output.")

# === 🔧 Extract Tool Calls ===
def extract_tools(text):
    matches = re.findall(r"(search_song\\s*\\(.*?\\)|create_playlist\\s*\\(.*?\\))", text, re.DOTALL)
    return matches

# === ⚡ Execute Tool Calls ===
def execute_tool_call(tool_call, user_id, previous_output=None):
    try:
        if previous_output and "track_uris" in previous_output:
            uris_str = str(previous_output["track_uris"])
            tool_call = tool_call.replace("[track_uris]", uris_str)
        func_name = tool_call.split("(")[0].strip()
        args_str = tool_call[len(func_name) + 1:-1]
        args = ast.literal_eval(f"[{args_str}]")
        if func_name == "create_playlist":
            return create_playlist(user_id, *args)
        elif func_name == "search_song":
            return search_song(*args, limit=30)
    except Exception as e:
        logging.error(f"[DEBUG] Error executing tool call: {str(e)}")

# === 🎵 Create Playlist Function ===
def create_playlist(user_id, playlist_name, description, track_uris):
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)



