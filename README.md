# Teleprompt - AI Drawing Game

A multiplayer web game similar to Gartic Phone, but with AI image generation using OpenAI's DALL-E 3 model.

## Features

- 🎨 Real-time multiplayer gameplay with WebSockets
- 🤖 AI image generation using OpenAI DALL-E 3 model
- ⏱️ Time-limited prompts (20 seconds)
- 🎯 Configurable player count (default: 4 players, minimum: 2)
- 👑 Room creator can start game manually with any number of players
- 📱 Responsive design with Tailwind CSS
- 🎲 Fallback to random DALL-E generated images if AI generation fails
- ⏳ Real-time loading indicators during image generation

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up OpenAI API key:**
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```
   
   Get your API key at: https://platform.openai.com/api-keys

3. **Run the application:**
   ```bash
   python app.py
   ```

4. **Open your browser:**
   Navigate to `http://localhost:8000`

## How to Play

1. **Join a Game:**
   - Enter your name and a room code
   - Or create a new room by clicking "Create New Room"

2. **Wait for Players:**
   - Game starts automatically when 4 players join
   - Room creator can start manually with 2+ players using "Start Game Now" button
   - You'll see all players in the lobby

3. **Play the Game:**
   - Each player gets 20 seconds to describe the current image
   - AI generates a new image using DALL-E 3 based on your prompt
   - All players see a loading wheel during image generation
   - The chain continues until all players have had a turn

4. **View Results:**
   - See the complete chain of prompts and generated images
   - Share your creative journey with friends!

## Game Flow

1. **Round 1:** First player sees a random stock image and writes a prompt
2. **Round 2:** Second player sees the AI-generated image and writes a new prompt
3. **Continue:** Process repeats for all players
4. **Results:** View the complete creative chain

## Configuration

- **MIN_PLAYERS:** Minimum players required to start (default: 4)
- **PROMPT_TIMEOUT:** Time limit for prompts in seconds (default: 20)
- **HUGGINGFACE_API_URL:** Model endpoint for image generation

## File Structure

```
teleprompt/
├── app.py                 # Flask application with SocketIO
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── lobby.html        # Game lobby/join page
│   ├── game.html         # Main game interface
│   └── results.html      # Results display
└── static/               # Static assets
    ├── generated/        # AI-generated images
    └── img/             # Stock images for fallback
        ├── stock1.svg
        ├── stock2.svg
        ├── stock3.svg
        └── stock4.svg
```

## Technology Stack

- **Backend:** Python Flask + Flask-SocketIO
- **Frontend:** HTML + Tailwind CSS + Vanilla JavaScript
- **AI:** OpenAI DALL-E 3 API
- **Real-time:** WebSockets for multiplayer communication

## Troubleshooting

- **No images generating:** Check your OpenAI API key
- **Connection issues:** Ensure all players are on the same network
- **Game not starting:** Make sure you have at least 4 players

## Color Scheme

The application uses a white and blue color scheme as requested:
- Primary blue: #4F46E5
- Secondary blue: #7C3AED
- Accent blue: #059669
- Background: Gradient from blue to purple
