#!/usr/bin/env bash
# Deploy Campus Time Ops to Cloud Run (asia-southeast1): backend (REST + MCP) and dashboard.
# Prereqs: gcloud auth login; gcloud config set project <GCP_PROJECT>. See docs/SETUP_GOOGLE.md.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${GCP_PROJECT:-$(gcloud config get-value project)}"
REGION="${REGION:-asia-southeast1}"
REPO="${AR_REPO:-campus-time-ops}"
TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%s)"
BACKEND_IMG="$REGION-docker.pkg.dev/$PROJECT/$REPO/backend:$TAG"
FRONTEND_IMG="$REGION-docker.pkg.dev/$PROJECT/$REPO/dashboard:$TAG"
SA="campus-time-ops@$PROJECT.iam.gserviceaccount.com"

echo "==> project=$PROJECT region=$REGION tag=$TAG"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com firestore.googleapis.com --project "$PROJECT" >/dev/null

gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION" --project "$PROJECT"

gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1 || \
  gcloud iam service-accounts create campus-time-ops --display-name "Campus Time Ops runtime" --project "$PROJECT"
for role in roles/datastore.user roles/secretmanager.secretAccessor roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role "$role" --condition None >/dev/null
done

# Secrets (created once; values from env or generated)
if ! gcloud secrets describe MCP_AUTH_TOKEN --project "$PROJECT" >/dev/null 2>&1; then
  printf '%s' "${MCP_AUTH_TOKEN:-$(openssl rand -hex 32)}" | gcloud secrets create MCP_AUTH_TOKEN --data-file=- --project "$PROJECT"
fi
SECRETS="MCP_AUTH_TOKEN=MCP_AUTH_TOKEN:latest"
EXTRA_ENV=""
if gcloud secrets describe GOOGLE_OAUTH_TOKEN --project "$PROJECT" >/dev/null 2>&1; then
  # authorized_user JSON for the DEMO Workspace account -> mounted as a file; enables real Calendar/Gmail drafts/Docs
  SECRETS="$SECRETS,/secrets/oauth/token.json=GOOGLE_OAUTH_TOKEN:latest"
  EXTRA_ENV=",WORKSPACE_MODE=google,GOOGLE_OAUTH_TOKEN_FILE=/secrets/oauth/token.json"
fi

echo "==> build backend"
cat > /tmp/cto-backend-build.yaml <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: [build, -f, backend/Dockerfile, -t, $BACKEND_IMG, .]
images: [$BACKEND_IMG]
EOF
gcloud builds submit --config /tmp/cto-backend-build.yaml --project "$PROJECT" .

echo "==> deploy backend"
gcloud run deploy campus-time-ops-api --image "$BACKEND_IMG" --region "$REGION" --project "$PROJECT" \
  --service-account "$SA" --allow-unauthenticated --memory 2Gi --cpu 2 --min-instances 1 --max-instances 1 \
  --concurrency 40 --timeout 120 \
  --set-secrets "$SECRETS" \
  --set-env-vars "STORE_BACKEND=firestore,GCP_PROJECT=$PROJECT,DATA_MODE=${DATA_MODE:-snapshot},WORKSPACE_DEMO_DOMAIN=${WORKSPACE_DEMO_DOMAIN:-demo.example.edu},REQUIRE_API_AUTH=true,GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-pro}$EXTRA_ENV"
API_URL="$(gcloud run services describe campus-time-ops-api --region "$REGION" --project "$PROJECT" --format 'value(status.url)')"
gcloud run services update campus-time-ops-api --region "$REGION" --project "$PROJECT" --update-env-vars "PUBLIC_BASE_URL=$API_URL" >/dev/null

echo "==> build + deploy dashboard"
gcloud builds submit frontend --tag "$FRONTEND_IMG" --project "$PROJECT"
gcloud run deploy campus-time-ops-dashboard --image "$FRONTEND_IMG" --region "$REGION" --project "$PROJECT" \
  --service-account "$SA" --allow-unauthenticated --memory 512Mi \
  --set-secrets "MCP_AUTH_TOKEN=MCP_AUTH_TOKEN:latest" --set-env-vars "BACKEND_URL=$API_URL"
DASH_URL="$(gcloud run services describe campus-time-ops-dashboard --region "$REGION" --project "$PROJECT" --format 'value(status.url)')"
gcloud run services update campus-time-ops-api --region "$REGION" --project "$PROJECT" --update-env-vars "DASHBOARD_BASE_URL=$DASH_URL" >/dev/null

echo
echo "Backend  : $API_URL   (REST /api, MCP $API_URL/mcp - bearer token in Secret Manager: MCP_AUTH_TOKEN)"
echo "Dashboard: $DASH_URL"
echo "Seed a clean demo state: BACKEND_URL=$API_URL MCP_AUTH_TOKEN=\$(gcloud secrets versions access latest --secret MCP_AUTH_TOKEN) make reset-demo"
