# Deploying Video Downloader to GCP Cloud Run (Free Tier)

This guide walks you through deploying the video downloader web app to Google Cloud Platform's Cloud Run service while staying within the free tier limits.

## Features

- **Password Protected** - Only you can access and use the app
- **Mobile Optimized** - Works great on your phone
- **30-Day Sessions** - Stay logged in on your devices
- **Scales to Zero** - No cost when not in use

## GCP Free Tier Limits (Cloud Run)

- **2 million requests/month**
- **360,000 GB-seconds of compute/month**
- **180,000 vCPU-seconds/month**
- The app scales to zero when not in use (no cost when idle)

## Prerequisites

1. A Google Cloud Platform account
2. `gcloud` CLI installed ([Install guide](https://cloud.google.com/sdk/docs/install))
3. Docker installed (for local testing)

## Quick Deploy (5 minutes)

### Step 1: Set up GCP Project

```bash
# Login to GCP
gcloud auth login

# Create a new project (or use existing)
gcloud projects create video-downloader-app --name="Video Downloader"

# Set as current project
gcloud config set project video-downloader-app

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

### Step 2: Create Artifact Registry Repository

```bash
# Create a Docker repository
gcloud artifacts repositories create video-dl \
    --repository-format=docker \
    --location=us-central1 \
    --description="Video Downloader Docker images"
```

### Step 3: Build and Deploy

**Option A: Use the deploy script (recommended)**

```bash
cd /path/to/youtube-dl

# Run the deploy script - it will prompt for a password
./deploy.sh your-project-id

# Or provide password directly
./deploy.sh your-project-id "your-secure-password"
```

**Option B: Manual deployment**

```bash
# Navigate to the project directory
cd /path/to/youtube-dl

# Build and submit to Cloud Build
gcloud builds submit --tag us-central1-docker.pkg.dev/video-downloader-app/video-dl/webapp:latest

# Generate a secret key
SECRET_KEY=$(openssl rand -hex 32)

# Deploy to Cloud Run with password protection
gcloud run deploy video-downloader \
    --image us-central1-docker.pkg.dev/video-downloader-app/video-dl/webapp:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --timeout 300 \
    --max-instances 2 \
    --set-env-vars "MAX_DURATION=600,APP_PASSWORD=your-password-here,SECRET_KEY=$SECRET_KEY"
```

### Step 4: Access Your App

After deployment, you'll see a URL like:
```
https://video-downloader-xxxxxx-uc.a.run.app
```

Open this URL on your phone to download videos!

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_PASSWORD` | (none) | Password to access the app. If not set, app is public |
| `SECRET_KEY` | (auto) | Secret key for session signing. Auto-generated if not set |
| `MAX_DURATION` | 600 | Maximum video duration in seconds (10 min) |
| `PORT` | 8080 | Server port (set automatically by Cloud Run) |

### Managing Authentication

**Change password:**
```bash
gcloud run services update video-downloader \
    --region us-central1 \
    --set-env-vars "APP_PASSWORD=new-password"
```

**Remove password (make app public):**
```bash
gcloud run services update video-downloader \
    --region us-central1 \
    --remove-env-vars "APP_PASSWORD"
```

**Note:** Sessions are stored in browser cookies for 30 days. After changing the password, existing sessions remain valid until they expire or the user logs out.

### Adjusting Limits

To allow longer videos (uses more memory/time):

```bash
gcloud run deploy video-downloader \
    --image us-central1-docker.pkg.dev/video-downloader-app/video-dl/webapp:latest \
    --memory 1Gi \
    --timeout 600 \
    --set-env-vars "MAX_DURATION=1200"
```

## Local Testing

### Using Docker

```bash
# Build the image
docker build -t video-dl .

# Run locally
docker run -p 8080:8080 video-dl

# Open http://localhost:8080
```

### Without Docker

```bash
cd webapp
pip install -r requirements.txt
python app.py

# Open http://localhost:8080
```

## Cost Optimization Tips

1. **Keep MAX_DURATION low** - Shorter videos = less compute time
2. **Use minimum memory** - 512Mi should work for most videos
3. **Set max-instances to 2** - Prevents runaway scaling
4. **Scale to zero** - Cloud Run automatically stops when idle

## Troubleshooting

### "Video too long" error
Increase `MAX_DURATION` environment variable or the video exceeds your limit.

### Download fails
- Some videos may be geo-restricted or require authentication
- Try a different quality setting
- Check Cloud Run logs: `gcloud run logs read video-downloader`

### Slow downloads
- Cloud Run has bandwidth limits; large videos may be slow
- Consider using Cloud Storage for temporary file caching

### Out of memory
Increase memory allocation:
```bash
gcloud run services update video-downloader --memory 1Gi
```

## Updating the App

To deploy updates:

```bash
# Rebuild and submit
gcloud builds submit --tag us-central1-docker.pkg.dev/video-downloader-app/video-dl/webapp:latest

# Redeploy
gcloud run deploy video-downloader \
    --image us-central1-docker.pkg.dev/video-downloader-app/video-dl/webapp:latest
```

## Security Notes

- The app is deployed with `--allow-unauthenticated` for easy access
- To restrict access, remove this flag and configure IAM
- Consider adding rate limiting for production use
- Be aware of YouTube's Terms of Service regarding video downloads

## Add to Home Screen (Mobile)

For quick access on your phone:

**iOS Safari:**
1. Open the app URL
2. Tap Share icon
3. Tap "Add to Home Screen"

**Android Chrome:**
1. Open the app URL
2. Tap menu (three dots)
3. Tap "Add to Home screen"
