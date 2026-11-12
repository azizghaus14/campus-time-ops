# Campus Time Ops: website + backend in ONE container (Hugging Face Spaces, Docker SDK).
# Build context = the staged folder produced by scripts/build_hf_space.sh
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
ENV NEXT_TELEMETRY_DISABLED=1 BACKEND_URL=http://127.0.0.1:8000
RUN npm run build

FROM python:3.12-slim
COPY --from=web /usr/local/bin/node /usr/local/bin/node
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    REPO_ROOT=/srv DATA_DIR=/srv/data STATE_DIR=/tmp/state OUTBOX_DIR=/tmp/outbox \
    DATA_MODE=snapshot WORKSPACE_MODE=local NEXT_TELEMETRY_DISABLED=1
RUN pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "mcp[cli]>=1.9,<2" "ortools>=9.12" \
      "pydantic>=2.7" requests python-dotenv pillow python-multipart
WORKDIR /srv
COPY backend/app backend/app
COPY data data
COPY grounding/campus_ops_policy.md grounding/campus_ops_policy.md
COPY --from=web /web/.next/standalone web/
COPY --from=web /web/.next/static web/.next/static
COPY --from=web /web/public web/public
COPY start.sh /srv/start.sh
RUN chmod -R a+rX /srv
EXPOSE 7860
CMD ["sh", "/srv/start.sh"]
