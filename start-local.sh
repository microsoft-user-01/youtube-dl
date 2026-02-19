#!/bin/bash
# Start Video Downloader locally with Cloudflare Tunnel

cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export APP_PASSWORD="video-downloader-app"
export MAX_DURATION=3600  # 60 minutes for local
export PORT=8080
export SECRET_KEY="local-dev-key-12345"
export COOKIES_FROM_BROWSER="brave"  # Use Brave browser cookies
export FLASK_APP=webapp/app.py

# Kill any existing processes
echo "Stopping any existing processes..."
pkill -f "flask run.*8080" 2>/dev/null
pkill -f "python.*app.py" 2>/dev/null
pkill -f "cloudflared.*tunnel" 2>/dev/null
sleep 2

# Start the web server
echo "Starting web server on port $PORT..."
cd webapp
flask run --host 0.0.0.0 --port $PORT 2>&1 &
FLASK_PID=$!
cd ..

# Wait for server to start
sleep 3

# Check server is running
if ! curl -s http://localhost:$PORT/health > /dev/null; then
    echo "ERROR: Server failed to start"
    exit 1
fi

echo "Server started (PID: $FLASK_PID)"

# Start Cloudflare Tunnel
echo ""
echo "Starting Cloudflare Tunnel..."
echo "============================================"
~/cloudflared tunnel --url http://localhost:$PORT 2>&1 &
TUNNEL_PID=$!

sleep 8

echo ""
echo "Password: $APP_PASSWORD"
echo "Max video duration: 60 minutes"
echo ""
echo "Press Ctrl+C to stop both services"
echo "============================================"

# Wait for Ctrl+C
trap "pkill -f 'flask run.*8080'; pkill -f cloudflared; exit" INT TERM
wait
