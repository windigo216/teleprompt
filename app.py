from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import requests
import json
import os
import random
import time
from datetime import datetime
import uuid
import numpy as np
import base64
from PIL import Image
from io import BytesIO
from openai import OpenAI
from dotenv import load_dotenv

# Set your API key
load_dotenv(".env")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Game state storage (in production, use Redis or database)
games = {}
rooms = {}
room_creators = {}  # Track who created each room

# Configuration
MIN_PLAYERS = 4
PROMPT_TIMEOUT = 20  # seconds, 'your-token-here'
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Ensure static directories exist
os.makedirs('static/generated', exist_ok=True)
os.makedirs('static/img', exist_ok=True)

def generate_image(prompt, room_code):
    """Generate image using OpenAI DALL-E model"""
    try:
        # Generate image using OpenAI DALL-E (older API version)
        response = client.images.generate(
            model="dall-e-2",
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        
        # Get the image URL and download it
        image_url = response.data[0].url
        image_response = requests.get(image_url)
        image_bytes = image_response.content
        
        # Convert the bytes to a PIL Image
        image = Image.open(BytesIO(image_bytes))
        
        # Convert PIL Image to numpy array
        numpy_array = np.array(image)
        
        # Save generated image
        image_id = str(uuid.uuid4())
        image_path = f"static/generated/{image_id}.png"
        
        # Save the PIL image directly
        image.save(image_path, "PNG")
        
        print(f"Generated image for prompt: '{prompt}' -> {image_path}")
        return image_path
        
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

def get_random_stock_image():
    """Generate a random DALL-E image as fallback"""
    try:
        # Generate a random creative prompt for fallback
        fallback_prompts = [
            "A beautiful abstract painting with vibrant colors",
            "A serene landscape with mountains and a lake",
            "A futuristic city skyline at sunset",
            "A magical forest with glowing trees",
            "A cosmic galaxy with swirling stars"
        ]
        
        random_prompt = random.choice(fallback_prompts)
        print(f"Generating fallback image with prompt: '{random_prompt}'")
        
        # Generate image using OpenAI DALL-E (older API version)
        response = client.images.generate(
            model="dall-e-2",
            prompt=random_prompt,
            n=1,
            size="1024x1024"
        )
        
        # Get the image URL and download it
        image_url = response.data[0].url
        image_response = requests.get(image_url)
        image_bytes = image_response.content
        
        # Convert the bytes to a PIL Image
        image = Image.open(BytesIO(image_bytes))
        
        # Convert PIL Image to numpy array
        numpy_array = np.array(image)
        
        # Save generated image
        image_id = str(uuid.uuid4())
        image_path = f"static/generated/{image_id}.png"
        
        # Save the PIL image directly
        image.save(image_path, "PNG")
        
        print(f"Generated fallback image: {image_path}")
        return image_path
        
    except Exception as e:
        print(f"Error generating fallback image: {e}")
        return None

@app.route('/')
def index():
    return render_template('lobby.html')

@app.route('/game/<room_code>')
def game(room_code):
    return render_template('game.html', room_code=room_code)

@app.route('/results/<room_code>')
def results(room_code):
    if room_code in games:
        return render_template('results.html', game=games[room_code])
    return "Game not found", 404

@socketio.on('join_room')
def handle_join_room(data):
    room_code = data['room_code']
    player_name = data['player_name']
    is_creator = data.get('is_creator', False)
    
    if room_code not in rooms:
        rooms[room_code] = []
        if is_creator:
            room_creators[room_code] = player_name
    
    if len(rooms[room_code]) >= MIN_PLAYERS and not any(p['name'] == player_name for p in rooms[room_code]):
        emit('room_full', {'message': 'Room is full'})
        return
    
    # Add or update player
    player_exists = False
    for i, player in enumerate(rooms[room_code]):
        if player['name'] == player_name:
            # Update existing player's socket ID
            rooms[room_code][i]['id'] = request.sid
            player_exists = True
            break
    
    if not player_exists:
        # Only add new player if they don't already exist
        rooms[room_code].append({'name': player_name, 'id': request.sid})
    
    join_room(room_code)
    join_room(request.sid)  # Also join the player to their individual socket room
    
    # Check if this player is the room creator
    is_room_creator = room_creators.get(room_code) == player_name
    
    # Send personal confirmation to the joining player
    emit('player_joined', {
        'player_name': player_name,
        'players': [p['name'] for p in rooms[room_code]],
        'ready_to_start': len(rooms[room_code]) >= MIN_PLAYERS,
        'is_creator': is_room_creator
    })
    
    # Notify other players in the room about the new player
    emit('player_list_updated', {
        'players': [p['name'] for p in rooms[room_code]],
        'ready_to_start': len(rooms[room_code]) >= MIN_PLAYERS
    }, room=room_code)
    
    # If game is already running, send current game state to the joining player
    if room_code in games:
        game = games[room_code]
        current_player = game['players'][game['current_player']]['name']
        
        # Send current image if available
        current_image = None
        if game['images']:
            current_image = game['images'][-1]['path']
        
        # Send game state update only to the joining player
        emit('game_state_update', {
            'current_player': current_player,
            'round': game['current_round'],
            'image': current_image,
            'timeout': PROMPT_TIMEOUT,
            'players': [p['name'] for p in game['players']],
            'is_my_turn': current_player == player_name
        })
    
    # Game no longer auto-starts at MIN_PLAYERS
    # Room creator must manually start the game

@socketio.on('start_game_manual')
def handle_start_game_manual(data):
    room_code = data['room_code']
    player_name = data['player_name']
    
    # Check if player is the room creator
    if room_creators.get(room_code) != player_name:
        emit('error', {'message': 'Only the room creator can start the game manually'})
        return
    
    # Check if there are at least 2 players
    if len(rooms[room_code]) < 2:
        emit('error', {'message': 'Need at least 2 players to start the game'})
        return
    
    # Check if game is already running
    if room_code in games:
        emit('error', {'message': 'Game is already running'})
        return
    
    # Start the game
    start_game(room_code)

def get_random_static_image():
    """Get a random image from the static/img folder"""
    import random
    import os
    
    static_img_dir = 'static/img'
    if not os.path.exists(static_img_dir):
        return '/static/img/placeholder.svg'
    
    # Get all image files from static/img
    image_files = []
    for file in os.listdir(static_img_dir):
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
            image_files.append(f'/static/img/{file}')
    
    if not image_files:
        return '/static/img/placeholder.svg'
    
    return random.choice(image_files)

def start_game(room_code):
    """Initialize and start a new game"""
    players = rooms[room_code]
    game_id = str(uuid.uuid4())
    
    # Get a random starting image
    starting_image = get_random_static_image()
    
    games[room_code] = {
        'id': game_id,
        'players': [{'name': p['name'], 'id': p['id']} for p in players],
        'current_round': 0,
        'current_player': 0,
        'prompts': [],
        'images': [{'path': starting_image, 'prompt': 'Starting image'}],
        'status': 'waiting_for_prompt',
        'start_time': time.time(),
        'round_start_time': time.time()
    }
    
    # Send game_started event to all players in the room
    print(f"Starting game for room {room_code} with players: {[p['name'] for p in players]}")
    print(f"Starting image: {starting_image}")
    
    game_started_data = {
        'game_id': game_id,
        'players': [p['name'] for p in players],
        'current_player': players[0]['name'],
        'starting_image': starting_image
    }
    print(f"Emitting game_started event: {game_started_data}")
    emit('game_started', game_started_data, room=room_code)
    print(f"game_started event emitted to room {room_code}")

@socketio.on('submit_prompt')
def handle_submit_prompt(data):
    room_code = data['room_code']
    prompt = data['prompt']
    player_name = data['player_name']
    
    if room_code not in games:
        return
    
    game = games[room_code]
    
    # Check if it's this player's turn
    current_player = game['players'][game['current_player']]
    if current_player['name'] != player_name:
        emit('error', {'message': 'Not your turn'})
        return
    
    # Add prompt to game
    game['prompts'].append({
        'player': player_name,
        'text': prompt,
        'round': game['current_round']
    })
    
    # Emit generating event to all players in the room
    emit('image_generating', {
        'player': player_name,
        'prompt': prompt
    }, room=room_code)
    
    # Generate image asynchronously using Flask-SocketIO background task
    def generate_and_continue():
        try:
            # Generate image
            image_path = generate_image(prompt, room_code)
            if not image_path:
                # Use random stock image if generation fails
                print(f"Image generation failed for prompt: '{prompt}', using fallback")
                image_path = get_random_stock_image()
            
            if image_path:
                game['images'].append({
                    'player': player_name,
                    'path': image_path,
                    'round': game['current_round']
                })
            else:
                # If even fallback fails, create a placeholder
                print("Both image generation and fallback failed, using placeholder")
                image_path = "static/img/placeholder.svg"
                game['images'].append({
                    'player': player_name,
                    'path': image_path,
                    'round': game['current_round']
                })
            
            # Move to next player
            game['current_player'] = (game['current_player'] + 1) % len(game['players'])
            game['current_round'] += 1
            game['round_start_time'] = time.time()
            
            # Check if game is complete
            if game['current_round'] >= len(game['players']):
                game['status'] = 'completed'
                socketio.emit('game_completed', {
                    'game_id': game['id'],
                    'prompts': game['prompts'],
                    'images': game['images']
                }, room=room_code)
            else:
                next_player = game['players'][game['current_player']]['name']
                # Emit next turn with image to all players
                socketio.emit('next_turn', {
                    'current_player': next_player,
                    'round': game['current_round'],
                    'image': image_path,
                    'timeout': PROMPT_TIMEOUT,
                    'start_timer': True  # Signal to start timer
                }, room=room_code)
        except Exception as e:
            print(f"Error in generate_and_continue: {e}")
            # Emit error event to hide loading wheel
            socketio.emit('image_generation_error', {
                'error': 'Image generation failed'
            }, room=room_code)
    
    # Start image generation in a background task
    socketio.start_background_task(generate_and_continue)

@socketio.on('timeout_prompt')
def handle_timeout_prompt(data):
    room_code = data['room_code']
    
    if room_code not in games:
        return
    
    game = games[room_code]
    current_player = game['players'][game['current_player']]['name']
    
    # Use random stock image
    image_path = get_random_stock_image()
    if image_path:
        game['images'].append({
            'player': current_player,
            'path': image_path,
            'round': game['current_round']
        })
    
    # Move to next player
    game['current_player'] = (game['current_player'] + 1) % len(game['players'])
    game['current_round'] += 1
    game['round_start_time'] = time.time()
    
    # Check if game is complete
    if game['current_round'] >= len(game['players']):
        game['status'] = 'completed'
        emit('game_completed', {
            'game_id': game['id'],
            'prompts': game['prompts'],
            'images': game['images']
        }, room=room_code)
    else:
        next_player = game['players'][game['current_player']]['name']
        # Emit next turn with image to all players
        emit('next_turn', {
            'current_player': next_player,
            'round': game['current_round'],
            'image': image_path,
            'timeout': PROMPT_TIMEOUT,
            'start_timer': True  # Start timer for timeout case too
        }, room=room_code)

@socketio.on('disconnect')
def handle_disconnect():
    # Remove player from all rooms
    # Create a copy of the dictionary to avoid modification during iteration
    rooms_copy = dict(rooms)
    for room_code, players in rooms_copy.items():
        rooms[room_code] = [p for p in players if p['id'] != request.sid]
        
        if len(rooms[room_code]) == 0:
            del rooms[room_code]
        else:
            emit('player_list_updated', {
                'players': [p['name'] for p in rooms[room_code]],
                'ready_to_start': len(rooms[room_code]) >= MIN_PLAYERS
            }, room=room_code)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)
