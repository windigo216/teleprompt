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
room_settings = {}  # Store settings per room

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

@app.route('/inverted-game/<room_code>')
def inverted_game(room_code):
    return render_template('inverted-game.html', room_code=room_code)

@app.route('/results/<room_code>')
def results(room_code):
    if room_code in games:
        game = games[room_code]
        # Clean up old completed games (older than 1 hour)
        if game.get('status') == 'completed' and time.time() - game.get('completion_time', game.get('start_time', 0)) > 3600:
            del games[room_code]
            return "Game not found", 404
        return render_template('results.html', game=game)
    return "Game not found", 404

@app.route('/canvas')
def canvas():
    return render_template('canvas.html')

@app.route('/save_canvas', methods=['POST'])
def save_canvas():
    try:
        data = request.get_json()
        image_data = data.get('image_data')
        format_type = data.get('format', 'png')
        
        if not image_data:
            return jsonify({'error': 'No image data provided'}), 400
        
        # Remove data URL prefix (e.g., "data:image/png;base64,")
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        # Decode base64 image data
        import base64
        image_bytes = base64.b64decode(image_data)
        
        # Create filename with timestamp
        import time
        timestamp = int(time.time())
        filename = f'canvas_drawing_{timestamp}.{format_type}'
        
        # Ensure the directory exists
        import os
        save_dir = 'static/canvas_drawings'
        os.makedirs(save_dir, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(save_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        
        return jsonify({
            'success': True, 
            'filename': filename,
            'path': f'/static/canvas_drawings/{filename}',
            'message': f'Drawing saved as {filename}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to save image: {str(e)}'}), 500

@socketio.on('join_room')
def handle_join_room(data):
    room_code = data['room_code']
    player_name = data['player_name']
    is_creator = data.get('is_creator', False)
    
    if room_code not in rooms:
        if not is_creator:
            emit('error', {'message': 'Room does not exist. Please create a new room or check the room code.'})
            return
        rooms[room_code] = []
        room_creators[room_code] = player_name
        room_settings[room_code] = {'time_limit': 20, 'gamemode': 'normal'}
    
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
        'is_creator': is_room_creator,
        'settings': room_settings[room_code]
    })
    
    # Notify other players in the room about the new player
    emit('player_list_updated', {
        'players': [p['name'] for p in rooms[room_code]],
        'ready_to_start': len(rooms[room_code]) >= MIN_PLAYERS,
        'creator': room_creators.get(room_code),
        'settings': room_settings[room_code]
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
            'timeout': room_settings.get(room_code, {}).get('time_limit', 20),
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

def describe_image(image_path):
    """
    Generate a text description of an image using GPT-4 Vision
    Based on test2.py implementation
    """
    try:
        # Encode the image
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Call the OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": "Describe this image in detail. It is a very rough outlined line drawing. The user had a specific non-abstract non-random goal when drawing this image. If the user had more time to continue (or was better at drawing), what would this be? Describe objects, colors, composition, style, and any text present. Your description should be detailed enough that someone could use it to try to recreate a similar image with an AI image generator. However, it must be short enough that someone can read it within 5 seconds or less (keep it to 20-30 words)."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        
        description = response.choices[0].message.content
        return description
        
    except Exception as e:
        print(f"Error describing image: {e}")
        return None

def start_game(room_code):
    """Initialize and start a new game"""
    players = rooms[room_code]
    game_id = str(uuid.uuid4())
    settings = room_settings.get(room_code, {'time_limit': 20, 'gamemode': 'normal'})
    gamemode = settings.get('gamemode', 'normal')
    
    if gamemode == 'inverted':
        # For inverted mode, provide a starting prompt for the first player to draw
        starting_prompt = "Draw whatever you want for the AI to analyze!"
        
        games[room_code] = {
            'id': game_id,
            'players': [{'name': p['name'], 'id': p['id']} for p in players],
            'current_round': 0,
            'current_player': 0,
            'prompts': [],
            'images': [],
            'descriptions': [],  # Store text descriptions
            'status': 'waiting_for_drawing',
            'start_time': time.time(),
            'round_start_time': time.time(),
            'gamemode': 'inverted'
        }
        
        # Send game_started event to all players in the room
        print(f"Starting inverted game for room {room_code} with players: {[p['name'] for p in players]}")
        
        game_started_data = {
            'game_id': game_id,
            'players': [p['name'] for p in players],
            'current_player': players[0]['name'],
            'starting_prompt': starting_prompt,  # Starting prompt for first player to draw
            'settings': settings
        }
        print(f"Emitting game_started event: {game_started_data}")
        emit('game_started', game_started_data, room=room_code)
        print(f"game_started event emitted to room {room_code}")
    else:
        # Normal mode - use stock1.svg for player 1
        starting_image = f'static/img/starting-img.png'
        
        games[room_code] = {
            'id': game_id,
            'players': [{'name': p['name'], 'id': p['id']} for p in players],
            'current_round': 0,
            'current_player': 0,
            'prompts': [],
            'images': [{'path': starting_image, 'prompt': 'Starting image'}],
            'status': 'waiting_for_prompt',
            'start_time': time.time(),
            'round_start_time': time.time(),
            'gamemode': 'normal'
        }
        
        # Send game_started event to all players in the room
        print(f"Starting classic game for room {room_code} with players: {[p['name'] for p in players]}")
        print(f"Starting image: {starting_image}")
        
        game_started_data = {
            'game_id': game_id,
            'players': [p['name'] for p in players],
            'current_player': players[0]['name'],
            'starting_image': starting_image,
            'settings': settings
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
                game['completion_time'] = time.time()
                socketio.emit('game_completed', {
                    'game_id': game['id'],
                    'prompts': game['prompts'],
                    'images': game['images']
                }, room=room_code)
                # Clean up after game completion (keep game data for results page)
                if room_code in rooms:
                    del rooms[room_code]
                if room_code in room_creators:
                    del room_creators[room_code]
                if room_code in room_settings:
                    del room_settings[room_code]
            else:
                next_player = game['players'][game['current_player']]['name']
                # Emit next turn with image to all players
                socketio.emit('next_turn', {
                    'current_player': next_player,
                    'round': game['current_round'],
                    'image': image_path,
                    'timeout': room_settings.get(room_code, {}).get('time_limit', 20),
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

@socketio.on('submit_drawing')
def handle_submit_drawing(data):
    """Handle drawing submission for inverted game mode"""
    room_code = data['room_code']
    player_name = data['player_name']
    image_data = data['image_data']
    
    if room_code not in games:
        return
    
    game = games[room_code]
    
    # Check if it's inverted mode
    if game.get('gamemode') != 'inverted':
        emit('error', {'message': 'Not in inverted mode'})
        return
    
    # Check if it's this player's turn
    current_player = game['players'][game['current_player']]
    if current_player['name'] != player_name:
        emit('error', {'message': 'Not your turn'})
        return
    
    # Save the drawing
    try:
        # Remove data URL prefix (e.g., "data:image/png;base64,")
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        # Decode base64 image data
        image_bytes = base64.b64decode(image_data)
        
        # Create filename with timestamp
        timestamp = int(time.time())
        filename = f'drawing_{timestamp}_{player_name}.png'
        
        # Ensure the directory exists
        save_dir = 'static/canvas_drawings'
        os.makedirs(save_dir, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(save_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        
        # Add image to game
        game['images'].append({
            'player': player_name,
            'path': f'static/canvas_drawings/{filename}',
            'round': game['current_round']
        })
        
        # Emit processing event to all players
        emit('image_processing', {
            'player': player_name,
            'message': 'Processing your drawing...'
        }, room=room_code)
        
        # Process the drawing asynchronously
        def process_drawing_and_continue():
            try:
                # Describe the image using ChatGPT
                description = describe_image(file_path)
                if not description:
                    description = "A simple drawing"
                
                # Add description to game
                game['descriptions'].append({
                    'player': player_name,
                    'text': description,
                    'round': game['current_round']
                })
                
                # Move to next player
                game['current_player'] = (game['current_player'] + 1) % len(game['players'])
                game['current_round'] += 1
                game['round_start_time'] = time.time()
                
                # Check if game is complete
                if game['current_round'] >= len(game['players']):
                    game['status'] = 'completed'
                    game['completion_time'] = time.time()
                    socketio.emit('game_completed', {
                        'game_id': game['id'],
                        'prompts': game['descriptions'],  # Use descriptions instead of prompts
                        'images': game['images']
                    }, room=room_code)
                    # Clean up after game completion
                    if room_code in rooms:
                        del rooms[room_code]
                    if room_code in room_creators:
                        del room_creators[room_code]
                    if room_code in room_settings:
                        del room_settings[room_code]
                else:
                    next_player = game['players'][game['current_player']]['name']
                    # Emit next turn with description to all players
                    socketio.emit('next_turn_inverted', {
                        'current_player': next_player,
                        'round': game['current_round'],
                        'description': description,
                        'timeout': room_settings.get(room_code, {}).get('time_limit', 20),
                        'start_timer': True
                    }, room=room_code)
            except Exception as e:
                print(f"Error in process_drawing_and_continue: {e}")
                # Emit error event
                socketio.emit('image_processing_error', {
                    'error': 'Image processing failed'
                }, room=room_code)
        
        # Start image processing in a background task
        socketio.start_background_task(process_drawing_and_continue)
        
    except Exception as e:
        print(f"Error saving drawing: {e}")
        emit('error', {'message': 'Failed to save drawing'})

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
        game['completion_time'] = time.time()
        emit('game_completed', {
            'game_id': game['id'],
            'prompts': game['prompts'],
            'images': game['images']
        }, room=room_code)
        # Clean up after game completion (keep game data for results page)
        if room_code in rooms:
            del rooms[room_code]
        if room_code in room_creators:
            del room_creators[room_code]
        if room_code in room_settings:
            del room_settings[room_code]
    else:
        next_player = game['players'][game['current_player']]['name']
        # Emit next turn with image to all players
        emit('next_turn', {
            'current_player': next_player,
            'round': game['current_round'],
            'image': image_path,
            'timeout': room_settings.get(room_code, {}).get('time_limit', 20),
            'start_timer': True  # Start timer for timeout case too
        }, room=room_code)

@socketio.on('timeout_drawing')
def handle_timeout_drawing(data):
    """Handle drawing timeout for inverted game mode"""
    room_code = data['room_code']
    
    if room_code not in games:
        return
    
    game = games[room_code]
    current_player = game['players'][game['current_player']]['name']
    
    # Create a placeholder drawing
    placeholder_path = "static/img/placeholder.svg"
    game['images'].append({
        'player': current_player,
        'path': placeholder_path,
        'round': game['current_round']
    })
    
    # Add a default description
    game['descriptions'].append({
        'player': current_player,
        'text': "A simple drawing",
        'round': game['current_round']
    })
    
    # Move to next player
    game['current_player'] = (game['current_player'] + 1) % len(game['players'])
    game['current_round'] += 1
    game['round_start_time'] = time.time()
    
    # Check if game is complete
    if game['current_round'] >= len(game['players']):
        game['status'] = 'completed'
        game['completion_time'] = time.time()
        emit('game_completed', {
            'game_id': game['id'],
            'prompts': game['descriptions'],
            'images': game['images']
        }, room=room_code)
        # Clean up after game completion
        if room_code in rooms:
            del rooms[room_code]
        if room_code in room_creators:
            del room_creators[room_code]
        if room_code in room_settings:
            del room_settings[room_code]
    else:
        next_player = game['players'][game['current_player']]['name']
        # Emit next turn with description to all players
        emit('next_turn_inverted', {
            'current_player': next_player,
            'round': game['current_round'],
            'description': "A simple drawing",
            'timeout': room_settings.get(room_code, {}).get('time_limit', 20),
            'start_timer': True
        }, room=room_code)

@socketio.on('disconnect')
def handle_disconnect():
    # Remove player from all rooms
    # Create a copy of the dictionary to avoid modification during iteration
    rooms_copy = dict(rooms)
    for room_code, players in rooms_copy.items():
        rooms[room_code] = [p for p in players if p['id'] != request.sid]
        
        if len(rooms[room_code]) == 0:
            # Don't delete room if game is running
            if room_code not in games:
                del rooms[room_code]
                if room_code in room_creators:
                    del room_creators[room_code]
                if room_code in room_settings:
                    del room_settings[room_code]
        else:
            emit('player_list_updated', {
                'players': [p['name'] for p in rooms[room_code]],
                'ready_to_start': len(rooms[room_code]) >= MIN_PLAYERS,
                'creator': room_creators.get(room_code),
                'settings': room_settings.get(room_code, {'time_limit': 20, 'gamemode': 'normal'})
            }, room=room_code)

@socketio.on('get_game_state')
def handle_get_game_state(data):
    """Handle request for current game state"""
    print(f"🔍 get_game_state called with: {data}")
    room_code = data['room_code']
    player_name = data.get('player_name', 'Unknown')
    
    if room_code not in games:
        print(f"❌ No game found for room {room_code}")
        emit('error', {'message': 'No game found for this room'})
        return
    
    game = games[room_code]
    current_player = game['players'][game['current_player']]['name']
    print(f"🎮 Game found: {game.get('gamemode', 'normal')} mode, current player: {current_player}")
    
    # Send current game state
    if game.get('gamemode') == 'inverted':
        # For inverted mode, send the current description or starting prompt
        current_description = None
        if game['descriptions']:
            current_description = game['descriptions'][-1]['text']
        elif game['current_round'] == 0:
            # First round - send starting prompt
            current_description = "Draw whatever you want for the AI to analyze!"
        
        game_state_data = {
            'current_player': current_player,
            'round': game['current_round'],
            'description': current_description,
            'players': [p['name'] for p in game['players']],
            'is_my_turn': current_player == player_name,
            'timeout': room_settings.get(room_code, {}).get('time_limit', 20)
        }
        print(f"📤 Emitting game_state_update_inverted: {game_state_data}")
        emit('game_state_update_inverted', game_state_data)
    else:
        # For normal mode, send current image
        current_image = None
        if game['images']:
            current_image = game['images'][-1]['path']
        
        game_state_data = {
            'current_player': current_player,
            'round': game['current_round'],
            'image': current_image,
            'players': [p['name'] for p in game['players']],
            'is_my_turn': current_player == player_name,
            'timeout': room_settings.get(room_code, {}).get('time_limit', 20)
        }
        print(f"📤 Emitting game_state_update: {game_state_data}")
        emit('game_state_update', game_state_data)

@socketio.on('update_settings')
def handle_update_settings(data):
    room_code = data['room_code']
    player_name = data['player_name']
    new_settings = data['settings']
    
    # Check if player is the room creator
    if room_creators.get(room_code) != player_name:
        emit('error', {'message': 'Only the room creator can update settings'})
        return
    
    # Update settings
    room_settings[room_code].update(new_settings)
    
    # Notify all players in the room
    emit('settings_updated', {
        'settings': room_settings[room_code]
    }, room=room_code)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)
