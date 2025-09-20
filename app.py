from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import requests
import json
import os
import random
import time
from datetime import datetime
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Game state storage (in production, use Redis or database)
games = {}
rooms = {}
room_creators = {}  # Track who created each room

# Configuration
MIN_PLAYERS = 4
PROMPT_TIMEOUT = 20  # seconds
HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
HUGGINGFACE_API_TOKEN = os.getenv('HUGGINGFACE_API_TOKEN', 'your-token-here')

# Ensure static directories exist
os.makedirs('static/generated', exist_ok=True)
os.makedirs('static/img', exist_ok=True)

def generate_image(prompt, room_code):
    """Generate image using HuggingFace API"""
    try:
        headers = {"Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": 20,
                "guidance_scale": 7.5
            }
        }
        
        response = requests.post(HUGGINGFACE_API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            # Save generated image
            image_id = str(uuid.uuid4())
            image_path = f"static/generated/{image_id}.png"
            
            with open(image_path, 'wb') as f:
                f.write(response.content)
            
            return image_path
        else:
            print(f"HuggingFace API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

def get_random_stock_image():
    """Get a random stock image from /static/img/"""
    stock_images = []
    if os.path.exists('static/img'):
        stock_images = [f for f in os.listdir('static/img') if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if stock_images:
        return f"static/img/{random.choice(stock_images)}"
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
            rooms[room_code][i] = {'name': player_name, 'id': request.sid}
            player_exists = True
            break
    
    if not player_exists:
        rooms[room_code].append({'name': player_name, 'id': request.sid})
    
    join_room(room_code)
    
    # Check if this player is the room creator
    is_room_creator = room_creators.get(room_code) == player_name
    
    emit('player_joined', {
        'player_name': player_name,
        'players': [p['name'] for p in rooms[room_code]],
        'ready_to_start': len(rooms[room_code]) >= MIN_PLAYERS,
        'is_creator': is_room_creator
    }, room=room_code)
    
    # Start game if enough players
    if len(rooms[room_code]) >= MIN_PLAYERS and room_code not in games:
        start_game(room_code)

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

def start_game(room_code):
    """Initialize and start a new game"""
    players = rooms[room_code]
    game_id = str(uuid.uuid4())
    
    games[room_code] = {
        'id': game_id,
        'players': [{'name': p['name'], 'id': p['id']} for p in players],
        'current_round': 0,
        'current_player': 0,
        'prompts': [],
        'images': [],
        'status': 'waiting_for_prompt',
        'start_time': time.time(),
        'round_start_time': time.time()
    }
    
    emit('game_started', {
        'game_id': game_id,
        'players': [p['name'] for p in players],
        'current_player': players[0]['name']
    }, room=room_code)

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
    
    # Generate image
    image_path = generate_image(prompt, room_code)
    if not image_path:
        # Use random stock image if generation fails
        image_path = get_random_stock_image()
    
    if image_path:
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
        emit('game_completed', {
            'game_id': game['id'],
            'prompts': game['prompts'],
            'images': game['images']
        }, room=room_code)
    else:
        next_player = game['players'][game['current_player']]['name']
        emit('next_turn', {
            'current_player': next_player,
            'round': game['current_round'],
            'image': image_path,
            'timeout': PROMPT_TIMEOUT
        }, room=room_code)

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
        emit('next_turn', {
            'current_player': next_player,
            'round': game['current_round'],
            'image': image_path,
            'timeout': PROMPT_TIMEOUT
        }, room=room_code)

@socketio.on('disconnect')
def handle_disconnect():
    # Remove player from all rooms
    for room_code, players in rooms.items():
        rooms[room_code] = [p for p in players if p['id'] != request.sid]
        
        if len(rooms[room_code]) == 0:
            del rooms[room_code]
        else:
            emit('player_left', {
                'players': [p['name'] for p in rooms[room_code]],
                'ready_to_start': len(rooms[room_code]) >= MIN_PLAYERS
            }, room=room_code)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)
