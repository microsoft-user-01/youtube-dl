"""
YouTube Video Downloader Web App
Designed for GCP Cloud Run free tier deployment
"""
import os
import sys
import tempfile
import logging
import secrets
import hashlib
import hmac
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response, session, redirect, url_for
from functools import wraps
import re
import base64

# Use yt-dlp (actively maintained fork of youtube-dl)
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MAX_DURATION = int(os.environ.get('MAX_DURATION', 600))  # 10 min default limit
APP_PASSWORD = os.environ.get('APP_PASSWORD', '')  # Required for authentication
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))  # For session signing
YOUTUBE_COOKIES = os.environ.get('YOUTUBE_COOKIES', '')  # Base64 encoded cookies
COOKIES_FROM_BROWSER = os.environ.get('COOKIES_FROM_BROWSER', '')  # Browser name: chrome, firefox, brave, etc.

# Cookies file path
COOKIES_FILE = '/tmp/youtube_cookies.txt'

# Configure Flask session
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24 * 30  # 30 days


def init_cookies():
    """Initialize cookies from environment variable if present."""
    if YOUTUBE_COOKIES and not os.path.exists(COOKIES_FILE):
        try:
            cookies_data = base64.b64decode(YOUTUBE_COOKIES).decode('utf-8')
            with open(COOKIES_FILE, 'w') as f:
                f.write(cookies_data)
            logger.info("Loaded cookies from environment variable")
        except Exception as e:
            logger.error(f"Failed to load cookies from env: {e}")


# Initialize cookies on startup
init_cookies()


def require_auth(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip auth if no password is set (for local testing)
        if not APP_PASSWORD:
            return f(*args, **kwargs)
        
        # Check if user is authenticated
        if not session.get('authenticated'):
            if request.is_json:
                return jsonify({'error': 'Authentication required', 'redirect': '/login'}), 401
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function


def sanitize_filename(title):
    """Sanitize filename for safe download."""
    # Remove or replace invalid characters
    title = re.sub(r'[<>:"/\\|?*]', '', title)
    title = title.strip()
    return title[:100] if len(title) > 100 else title


class DownloadLogger:
    """Custom logger for youtube-dl."""
    def debug(self, msg):
        logger.debug(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def get_base_ydl_opts():
    """Get base yt-dlp options."""
    opts = {
        'quiet': True,
        'no_warnings': False,
        'logger': DownloadLogger(),
    }
    
    # Add cookies - prefer browser cookies for local installs
    if COOKIES_FROM_BROWSER:
        opts['cookiesfrombrowser'] = (COOKIES_FROM_BROWSER, None, None, None)
        logger.info(f"Using cookies from browser: {COOKIES_FROM_BROWSER}")
    elif os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
        logger.info("Using cookies file for authentication")
    
    return opts


def get_video_info(url):
    """Extract video info without downloading."""
    ydl_opts = get_base_ydl_opts()
    ydl_opts['extract_flat'] = False
    # Don't fail on format issues during info extraction
    ydl_opts['ignore_no_formats_error'] = True
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info


def download_video(url, format_id='best', audio_only=False, convert_mp3=False):
    """Download video and return file path."""
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = get_base_ydl_opts()
    ydl_opts.update({
        'format': 'bestaudio/best' if audio_only else format_id,
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,  # Only download single video
    })
    
    # Only convert to MP3 if explicitly requested (slower but universal)
    if audio_only and convert_mp3:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        
        # Find the downloaded file
        for file in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, file)
            if os.path.isfile(file_path):
                return file_path, info
    
    return None, None


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login."""
    # If no password set, redirect to main app
    if not APP_PASSWORD:
        return redirect(url_for('index'))
    
    # Already authenticated
    if session.get('authenticated'):
        return redirect(url_for('index'))
    
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(password, APP_PASSWORD):
            session['authenticated'] = True
            session.permanent = True  # Use permanent session (30 days)
            logger.info("User authenticated successfully")
            return redirect(url_for('index'))
        else:
            error = 'Invalid password'
            logger.warning("Failed login attempt")
    
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    """Handle logout."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@require_auth
def index():
    """Serve the main page."""
    has_cookies = os.path.exists(COOKIES_FILE)
    return render_template('index.html', has_cookies=has_cookies)


@app.route('/settings')
@require_auth
def settings():
    """Settings page for cookies."""
    has_cookies = os.path.exists(COOKIES_FILE)
    return render_template('settings.html', has_cookies=has_cookies)


@app.route('/api/cookies', methods=['POST'])
@require_auth
def api_set_cookies():
    """Set YouTube cookies."""
    try:
        data = request.get_json()
        cookies = data.get('cookies', '').strip()
        
        if not cookies:
            return jsonify({'error': 'Cookies are required'}), 400
        
        # Validate it looks like Netscape cookie format
        if not cookies.startswith('#') and '\t' not in cookies:
            return jsonify({'error': 'Invalid cookie format. Please use Netscape/Mozilla cookie format.'}), 400
        
        # Save cookies to file
        with open(COOKIES_FILE, 'w') as f:
            f.write(cookies)
        
        logger.info("Cookies saved successfully")
        return jsonify({'success': True, 'message': 'Cookies saved successfully'})
        
    except Exception as e:
        logger.error(f"Error saving cookies: {e}")
        return jsonify({'error': 'Failed to save cookies'}), 500


@app.route('/api/cookies', methods=['DELETE'])
@require_auth
def api_delete_cookies():
    """Delete YouTube cookies."""
    try:
        if os.path.exists(COOKIES_FILE):
            os.unlink(COOKIES_FILE)
        return jsonify({'success': True, 'message': 'Cookies deleted'})
    except Exception as e:
        logger.error(f"Error deleting cookies: {e}")
        return jsonify({'error': 'Failed to delete cookies'}), 500


@app.route('/api/cookies/status')
@require_auth
def api_cookies_status():
    """Check if cookies are configured."""
    return jsonify({'has_cookies': os.path.exists(COOKIES_FILE)})


@app.route('/api/search', methods=['POST'])
@require_auth
def api_search():
    """Search YouTube for videos."""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'error': 'Search query is required'}), 400
        
        ydl_opts = get_base_ydl_opts()
        ydl_opts['extract_flat'] = True
        ydl_opts['quiet'] = True
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Search YouTube for up to 10 results
            results = ydl.extract_info(f"ytsearch10:{query}", download=False)
            
            if not results or 'entries' not in results:
                return jsonify({'results': []})
            
            videos = []
            for entry in results['entries'][:10]:
                if entry and entry.get('id'):
                    duration = entry.get('duration') or 0
                    try:
                        duration = int(duration)
                        duration_str = f"{duration // 60}:{duration % 60:02d}"
                    except:
                        duration = 0
                        duration_str = "Unknown"
                    
                    videos.append({
                        'id': entry.get('id'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        'title': entry.get('title', 'Unknown'),
                        'duration': duration,
                        'duration_str': duration_str,
                        'thumbnail': entry.get('thumbnail') or f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg",
                        'channel': entry.get('channel') or entry.get('uploader', 'Unknown'),
                    })
            
            return jsonify({'results': videos})
            
    except Exception as e:
        import traceback
        logger.error(f"Search error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Search failed. Please try again.'}), 500


@app.route('/api/info', methods=['POST'])
@require_auth
def api_info():
    """Get video information without downloading."""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        info = get_video_info(url)
        
        if not info:
            return jsonify({'error': 'Could not extract video info'}), 400
        
        # Check duration limit
        duration = info.get('duration', 0) or 0
        if duration > MAX_DURATION:
            return jsonify({
                'error': f'Video too long. Max duration: {MAX_DURATION // 60} minutes'
            }), 400
        
        # Extract relevant formats
        formats = []
        if info.get('formats'):
            seen = set()
            for f in info['formats']:
                if f.get('format_id') and f.get('ext'):
                    # Create a readable label
                    height = f.get('height', '')
                    fps = f.get('fps', '')
                    ext = f.get('ext', '')
                    acodec = f.get('acodec', 'none')
                    vcodec = f.get('vcodec', 'none')
                    
                    # Skip formats without video for video downloads
                    if vcodec == 'none' and acodec != 'none':
                        label = f"Audio only ({ext})"
                    elif height:
                        label = f"{height}p"
                        if fps and fps > 30:
                            label += f" {fps}fps"
                        label += f" ({ext})"
                    else:
                        continue
                    
                    # Deduplicate
                    if label not in seen:
                        seen.add(label)
                        formats.append({
                            'format_id': f.get('format_id'),
                            'label': label,
                            'ext': ext,
                            'filesize': f.get('filesize') or f.get('filesize_approx'),
                        })
        
        # Sort formats by quality
        formats.sort(key=lambda x: (
            'Audio' not in x['label'],
            int(re.search(r'(\d+)p', x['label']).group(1)) if re.search(r'(\d+)p', x['label']) else 0
        ), reverse=True)
        
        return jsonify({
            'title': info.get('title', 'Unknown'),
            'thumbnail': info.get('thumbnail'),
            'duration': duration,
            'duration_str': f"{duration // 60}:{duration % 60:02d}" if duration else 'Unknown',
            'uploader': info.get('uploader', 'Unknown'),
            'formats': formats[:10],  # Limit to top 10 formats
        })
        
    except (DownloadError, ExtractorError) as e:
        error_msg = str(e)
        logger.error(f"Extraction error: {e}")
        
        # Check if it's a bot detection error
        if 'Sign in to confirm' in error_msg or 'bot' in error_msg.lower():
            return jsonify({
                'error': 'YouTube requires authentication. Please add your cookies in Settings.',
                'needs_cookies': True
            }), 400
        
        return jsonify({'error': 'Could not process this URL. It may be unsupported or restricted.'}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


@app.route('/api/download', methods=['GET', 'POST'])
@require_auth
def api_download():
    """Download video and return file."""
    try:
        # Support both GET (direct link) and POST (API call)
        if request.method == 'GET':
            url = request.args.get('url', '').strip()
            format_id = request.args.get('format_id', 'best')
            audio_only = request.args.get('audio_only', 'false').lower() == 'true'
            convert_mp3 = request.args.get('convert_mp3', 'false').lower() == 'true'
        else:
            data = request.get_json()
            url = data.get('url', '').strip()
            format_id = data.get('format_id', 'best')
            audio_only = data.get('audio_only', False)
            convert_mp3 = data.get('convert_mp3', False)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # First check video info
        info = get_video_info(url)
        duration = info.get('duration', 0) or 0
        if duration > MAX_DURATION:
            return jsonify({
                'error': f'Video too long. Max duration: {MAX_DURATION // 60} minutes'
            }), 400
        
        # Download the video
        file_path, info = download_video(url, format_id, audio_only, convert_mp3)
        
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': 'Download failed'}), 500
        
        # Get file info
        filename = os.path.basename(file_path)
        filesize = os.path.getsize(file_path)
        
        # Make filename ASCII-safe for mobile browsers
        safe_filename = ''.join(c if c.isalnum() or c in '.-_ ' else '_' for c in filename)
        
        # Determine MIME type
        ext = filename.rsplit('.', 1)[-1].lower()
        mime_types = {
            'mp4': 'video/mp4',
            'webm': 'audio/webm',  # Use audio/* for audio downloads
            'mkv': 'video/x-matroska',
            'mp3': 'audio/mpeg',
            'm4a': 'audio/mp4',
            'ogg': 'audio/ogg',
            'opus': 'audio/opus',
            'wav': 'audio/wav',
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')
        
        # For audio files, use octet-stream to force download on mobile
        if audio_only:
            mime_type = 'application/octet-stream'
        
        # Send file
        def generate():
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk
            # Clean up after sending
            try:
                os.unlink(file_path)
                os.rmdir(os.path.dirname(file_path))
            except:
                pass
        
        response = Response(generate(), mimetype=mime_type)
        response.headers['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
        response.headers['Content-Length'] = filesize
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
        
    except (DownloadError, ExtractorError) as e:
        logger.error(f"Download error: {e}")
        return jsonify({'error': 'Download failed. The video may be restricted or unavailable.'}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500


@app.route('/health')
def health():
    """Health check endpoint for Cloud Run."""
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'false').lower() == 'true')
