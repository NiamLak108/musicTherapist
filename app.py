import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from llmproxy import generate

app = Flask(__name__)

# Load environment variables
load_dotenv()

# Store user session data
user_sessions = {}

def generate_playlist(mood, genre):
    """Uses LLM to generate a playlist based on mood and genre, avoiding content filtering triggers."""
    response = generate(
        model="4o-mini",
        system="""
            You are a **music therapy assistant**. Your role is to generate **a 10-15 song playlist** 
            based strictly on the **user's mood and preferred genre**.
            
            - Keep responses **neutral and positive** to avoid triggering any content filtering.
            - If a user asks for a playlist, generate a **fun and engaging playlist name**.
            - Include a mix of **classic hits, underrated tracks, and popular songs**.
            - Format the output as:
              "**🎵 Playlist: [Generated Name]**\n
              1. [Song 1] - [Artist]\n
              2. [Song 2] - [Artist]\n
              ...
              10. [Song 10] - [Artist]"
            - No explanations or additional commentary, **just the playlist**.
        """,
        query=f"User mood: {mood}, Preferred genre: {genre}",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )
    
    return response.get("response", "⚠️ Sorry, I couldn't generate a playlist. Try again!")

@app.route('/query', methods=['POST'])
def handle_message():
    """Handles user input, extracts mood/genre, and generates a playlist."""
    data = request.get_json()
    user_id = data.get("user_name", "Unknown")
    message = data.get("text", "").strip().lower()

    if not message:
        return jsonify({"text": "🎵 Tell me your **mood** and **favorite genre**, and I'll create a custom playlist for you!"})

    # If user says "hi" or similar, return the last playlist if available
    if message in ["hi", "hello", "hey"] and user_id in user_sessions:
        last_playlist = user_sessions[user_id].get("playlist")
        if last_playlist:
            return jsonify({"text": f"🎶 Here's your last playlist:\n{last_playlist}"})
        return jsonify({"text": "🎵 Tell me your **mood** and **favorite genre**, and I'll create a new playlist for you!"})

    # Process input to extract mood and genre
    response = generate(
        model="4o-mini",
        system="""
            You are a **music assistant**. Your only job is to extract the user's **mood** and **music genre**.
            - If the user hasn't mentioned either, ask them casually.
            - Format the output as:
              "Mood: [mood]\nGenre: [genre]"
            - Keep responses **neutral and friendly** to prevent any content filtering.
        """,
        query=message,
        temperature=0.6,
        lastk=10,
        session_id=f"music-therapy-{user_id}",
        rag_usage=False
    )

    response_text = response.get("response", "").strip()

    # Extract mood and genre if detected
    if "mood:" in response_text.lower() and "genre:" in response_text.lower():
        lines = response_text.split("\n")
        mood = [line.split(":")[1].strip() for line in lines if "Mood:" in line][0]
        genre = [line.split(":")[1].strip() for line in lines if "Genre:" in line][0]

        # Generate playlist
        playlist = generate_playlist(mood, genre)
        
        # Store session info
        user_sessions[user_id] = {"mood": mood, "genre": genre, "playlist": playlist}
        
        return jsonify({"text": playlist})

    return jsonify({"text": response_text})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)













