# Build context: repository root  (docker build -f backend/Dockerfile .)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    REPO_ROOT=/srv DATA_DIR=/srv/data STATE_DIR=/tmp/state OUTBOX_DIR=/tmp/outbox PORT=8080
WORKDIR /srv

COPY backend/pyproject.toml backend/pyproject.toml
RUN pip install --upgrade pip && pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "mcp[cli]>=1.9,<2" "ortools>=9.12" \
      "pydantic>=2.7" requests python-dotenv pillow python-multipart \
      google-cloud-firestore google-api-python-client google-auth google-auth-oauthlib google-genai

COPY backend/app backend/app
COPY data data
COPY grounding/campus_ops_policy.md grounding/campus_ops_policy.md

WORKDIR /srv/backend
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
