import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from llmproxy import generate

app = Flask(__name__)

# Load environment variables
load_dotenv()

def generate_playlist(mood, genre):
    """Uses LLM to generate a playlist based on mood and genre."""
    response = generate(
        model="4o-mini",
        system="""
            You are a music recommendation assistant. Your job is to create a **10-song playlist** 
            based on the user's **mood and preferred genre**.
            - Generate fun and unique playlist names 🎵.
            - Include a mix of popular, underrated, and timeless songs.
            - Format output as:
              "**Playlist Name:** [Generated Name] 🎶\n
              1. [Song 1] - [Artist]\n
              2. [Song 2] - [Artist]\n
              ...
              10. [Song 10] - [Artist]"
            - Keep it **engaging, fun, and personalized**.
        """,
        query=f"User mood: {mood}, Preferred genre: {genre}",
        temperature=0.7,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )
    
    return response.get("response", "⚠️ Sorry, I couldn't generate a playlist. Try again!")

@app.route('/', methods=['POST'])
def handle_message():
    """Handles user input for mood and genre, then generates a playlist."""
    data = request.get_json()
    message = data.get("text", "").strip()

    if not message:
        return jsonify({"text": "⚠️ Please tell me how you're feeling and your favorite music genre!"})

    # Ask for mood and genre
    response = generate(
        model="4o-mini",
        system="""
            You are a friendly chatbot that helps users pick a **music playlist**.
            - If the user hasn't mentioned **mood** or **genre**, ask for them in a casual and fun way.
            - Keep the conversation **light and engaging** 🎵.
            - Once both are provided, confirm them and say: "Awesome! Let me create your playlist..."
        """,
        query=message,
        temperature=0.6,
        lastk=10,
        session_id="music-therapy-session",
        rag_usage=False
    )

    response_text = response.get("response", "").strip()

    # Extract mood and genre if detected
    if "mood:" in response_text.lower() and "genre:" in response_text.lower():
        mood, genre = response_text.split("mood:")[1].split("genre:")
        mood, genre = mood.strip(), genre.strip()
        playlist = generate_playlist(mood, genre)
        return jsonify({"text": playlist})
    
    return jsonify({"text": response_text})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)











