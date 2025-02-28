import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from llmproxy import generate

app = Flask(__name__)

# Load API Key from .env file
load_dotenv()

# Single user session
session = {
    "state": "conversation",
    "preferences": {"mood": None, "genre": None}
}

def music_assistant_llm(message):
    """Handles the full conversation and generates a playlist."""
    
    response = generate(
        model="4o-mini",
        system="""
            You are a **music therapy assistant** named MELODY 🎶. Your job is to create **personalized playlists** for users.
            
            - If it's the **first message**, say:
              "🎵 **WELCOME TO MELODY!** 🎶\nTell me how you're feeling and your favorite genre, and I'll create a **custom playlist just for you!**\n\nFor example:\n- "I'm feeling happy and I love pop!"\n- "I need some chill lo-fi beats."
            
            - Ask the user for their **mood and favorite music genre** if they haven't provided both yet.
            - Be **casual, friendly, and full of emojis** 🎧✨.
            - DO NOT repeat details that have already been collected.
            - Once both **mood** and **genre** are provided, confirm them and say:
              "Got it! I'll create a playlist based on your mood: [mood] and your genre: [genre]. 🎶\nGenerating your playlist now..."
              
            - Then, generate a **10-song playlist** based on the user's mood & genre.
            - Format the response as:
              "**🎵 Playlist: [Creative Playlist Name]**\n
              1. [Song 1] - [Artist]\n
              2. [Song 2] - [Artist]\n
              ...
              10. [Song 10] - [Artist]"
            
            - Keep it **engaging, fun, and simple** with no unnecessary text.
        """,
        query=f"User input: '{message}'\nCurrent preferences: {session['preferences']}",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )

    response_text = response.get("response", "⚠️ Sorry, I couldn't process that. Could you rephrase?").strip()

    return response_text


@app.route('/query', methods=['POST'])
def main():
    """Handles user messages and decides what to do."""
    data = request.get_json()
    message = data.get("text", "").strip()

    return jsonify({"text": music_assistant_llm(message)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)














