# YouTube Video Downloader Web App
# Optimized for GCP Cloud Run free tier

FROM python:3.11-slim

# Install ffmpeg, Node.js, and other dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g esbuild \
    && rm -rf /var/lib/apt/lists/* \
    && node --version \
    && npm --version

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY webapp/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy webapp (yt-dlp is installed from pip, no need for bundled youtube_dl)
COPY webapp/ ./webapp/

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV MAX_DURATION=600
# APP_PASSWORD should be set during deployment, not in Dockerfile
# SECRET_KEY will be auto-generated if not provided

# Expose port
EXPOSE 8080

# Run with gunicorn for production
WORKDIR /app/webapp
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "300", "--workers", "2", "app:app"]
