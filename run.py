#!/usr/bin/env python3
"""
Simple startup script for Teleprompt game
"""
import os
import sys

def main():
    # Check if HuggingFace token is set
    if not os.getenv('HUGGINGFACE_API_TOKEN'):
        print("⚠️  Warning: HUGGINGFACE_API_TOKEN not set!")
        print("   Set it with: export HUGGINGFACE_API_TOKEN='your-token-here'")
        print("   Get your free token at: https://huggingface.co/settings/tokens")
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
