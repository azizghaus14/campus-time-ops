#!/bin/sh
# Start the backend on an internal port, wait until it is healthy, then serve the website on the public port.
set -e
cd /srv/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 &
i=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" 2>/dev/null; do
  i=$((i+1)); [ $i -gt 120 ] && echo "backend failed to start" && exit 1; sleep 1
done
echo "backend ready"
cd /srv/web
export BACKEND_URL=http://127.0.0.1:8000 PORT=${PORT:-7860} HOSTNAME=0.0.0.0
exec node server.js
