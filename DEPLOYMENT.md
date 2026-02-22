# Google Cloud Deployment Instructions

## Prerequisites
- Google Cloud Project
- `gcloud` CLI installed and configured
- Docker installed (for local testing)

## Environment Variables
Set these in Google Cloud Secret Manager or Cloud Run environment:
```
OPENAI_API_KEY=your-api-key
DATABASE_URL=your-postgres-url  # For production
```

## Deploy to Google Cloud Run

### Option 1: Using Cloud Build (Automated)
```bash
git push origin main
# Cloud Build will automatically trigger if configured
```

### Option 2: Manual Deployment
```bash
# Set your project
gcloud config set project YOUR-PROJECT-ID

# Build and push image
gcloud builds submit --tag gcr.io/YOUR-PROJECT-ID/ai-playground

# Deploy to Cloud Run
gcloud run deploy ai-playground \
  --image gcr.io/YOUR-PROJECT-ID/ai-playground \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="OPENAI_API_KEY=YOUR-API-KEY,DATABASE_URL=YOUR-DB-URL"
```

### Option 3: Local Docker Testing
```bash
# Build locally
docker build -t ai-playground .

# Run locally
docker run -p 8080:8080 \
  -e OPENAI_API_KEY=your-api-key \
  -e DATABASE_URL=your-db-url \
  ai-playground
```

Visit `http://localhost:8080` to test.

## File Structure
- `Dockerfile` - Container configuration
- `.dockerignore` - Files to exclude from Docker build
- `cloudbuild.yaml` - Cloud Build CI/CD configuration

## Notes
- Default port: 8080 (Google Cloud standard)
- Uses gunicorn for production serving
- 4 workers, 2 threads per worker for optimal performance
- PostgreSQL recommended for production (DATABASE_URL env var)
- SQLite used if DATABASE_URL not set
