#!/usr/bin/env python3
"""
Simple startup script for Teleprompt game
"""
import os
import sys

def main():
    # Check if OpenAI API key is set
    if not os.getenv('OPENAI_API_KEY'):
        print("⚠️  Warning: OPENAI_API_KEY not set!")
        print("   Set it with: export OPENAI_API_KEY='your-api-key-here'")
        print("   Or create a .env file with: OPENAI_API_KEY=your-api-key-here")
        print("   Get your API key at: https://platform.openai.com/api-keys")
        print()
    
    # Import and run the app
    try:
        from app import app, socketio
        print("🚀 Starting Teleprompt game server...")
        print("   Open your browser to: http://localhost:8000")
        print("   Press Ctrl+C to stop the server")
        print()
        socketio.run(app, debug=True, host='0.0.0.0', port=8000)
    except ImportError as e:
        print(f"❌ Error importing app: {e}")
        print("   Make sure you've installed requirements: pip install -r requirements.txt")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Server stopped. Thanks for playing!")
        sys.exit(0)

if __name__ == '__main__':
    main()
