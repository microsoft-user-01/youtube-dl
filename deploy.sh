#!/bin/bash
# Deploy Video Downloader to GCP Cloud Run
# Usage: ./deploy.sh [PROJECT_ID] [PASSWORD]

set -e

# Configuration
PROJECT_ID="${1:-video-downloader-app}"
APP_PASSWORD="${2:-}"
REGION="us-central1"
SERVICE_NAME="video-downloader"
REPO_NAME="video-dl"
IMAGE_NAME="webapp"

echo "=== Video Downloader GCP Deployment ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI is not installed"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
    echo "Please login to GCP first:"
    echo "  gcloud auth login"
    exit 1
fi

# Prompt for password if not provided
if [ -z "$APP_PASSWORD" ]; then
    echo "Enter a password to secure your app (or press Enter to skip):"
    read -s APP_PASSWORD
    echo ""
    if [ -n "$APP_PASSWORD" ]; then
        echo "Confirm password:"
        read -s APP_PASSWORD_CONFIRM
        echo ""
        if [ "$APP_PASSWORD" != "$APP_PASSWORD_CONFIRM" ]; then
            echo "Error: Passwords don't match"
            exit 1
        fi
    fi
fi

# Generate a secret key for session signing
SECRET_KEY=$(openssl rand -hex 32)

# Set project
echo "Setting project to $PROJECT_ID..."
gcloud config set project "$PROJECT_ID" 2>/dev/null || {
    echo "Creating new project: $PROJECT_ID"
    gcloud projects create "$PROJECT_ID" --name="Video Downloader"
    gcloud config set project "$PROJECT_ID"
}

# Enable APIs
echo "Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet
gcloud services enable artifactregistry.googleapis.com --quiet

# Create Artifact Registry repo if it doesn't exist
echo "Setting up Artifact Registry..."
gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" 2>/dev/null || {
    gcloud artifacts repositories create "$REPO_NAME" \
        --repository-format=docker \
        --location="$REGION" \
        --description="Video Downloader Docker images"
}

# Build image
IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:latest"
echo "Building Docker image..."
gcloud builds submit --tag "$IMAGE_URI" .

# Build environment variables string
ENV_VARS="MAX_DURATION=600,SECRET_KEY=$SECRET_KEY"
if [ -n "$APP_PASSWORD" ]; then
    ENV_VARS="$ENV_VARS,APP_PASSWORD=$APP_PASSWORD"
    echo "Password protection: ENABLED"
else
    echo "Password protection: DISABLED (app is public)"
fi

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE_URI" \
    --platform managed \
    --region "$REGION" \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --timeout 300 \
    --max-instances 2 \
    --set-env-vars "$ENV_VARS"

# Get URL
URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(status.url)")

echo ""
echo "=== Deployment Complete ==="
echo "Your video downloader is live at:"
echo ""
echo "  $URL"
echo ""
if [ -n "$APP_PASSWORD" ]; then
    echo "Login with the password you set during deployment."
    echo ""
fi
echo "Open this URL on your phone to download videos!"
echo ""
echo "To add to home screen:"
echo "  iOS: Share > Add to Home Screen"
echo "  Android: Menu > Add to Home Screen"
echo ""
echo "To change the password later:"
echo "  gcloud run services update $SERVICE_NAME --set-env-vars APP_PASSWORD=newpassword"
