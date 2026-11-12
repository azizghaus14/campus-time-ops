# Google Cloud and Workspace setup (fresh project)

Every value in angle brackets is yours. The region is **asia-southeast1** throughout.

## 1. Project and tools
```bash
gcloud auth login
```
```bash
gcloud config set project <GCP_PROJECT>
```
You need billing enabled, Docker (optional: the deploy uses Cloud Build) and `make`.

## 2. Deploy the backend and dashboard
```bash
GCP_PROJECT=<GCP_PROJECT> WORKSPACE_DEMO_DOMAIN=<demo-domain> make deploy
```
`scripts/deploy.sh` does the following:
- enables Cloud Run, Artifact Registry, Cloud Build, Secret Manager and Firestore
- creates the `campus-time-ops` service account with **datastore.user**, **secretmanager.secretAccessor** and **aiplatform.user**
- creates the `MCP_AUTH_TOKEN` secret, with a random value if you don't supply one
- builds both images and deploys:
  - `campus-time-ops-api`: REST at `/api` and MCP at `/mcp`, with Firestore state and a single instance (D-12)
  - `campus-time-ops-dashboard`: Next.js, which proxies to the API with the token injected from Secret Manager

Create the Firestore database once, in Native mode, before the first deploy:
```bash
gcloud firestore databases create --location=asia-southeast1
```
Then seed a clean state:
```bash
BACKEND_URL=<api-url> MCP_AUTH_TOKEN=$(gcloud secrets versions access latest --secret MCP_AUTH_TOKEN) make reset-demo
```

## 3. Demo Workspace accounts (never real APU accounts)
1. In a demo Workspace domain, create `timetabling@`, `programme-leader@` and a few lecturer and student accounts. Address formats: lecturer `lect-<id>@<domain>`, intake `<intake>@students.<domain>`.
2. In Google Cloud, create an **OAuth client** of type "Desktop app". Run the consent flow once as `timetabling@<domain>`, with these scopes:
   `calendar.events`, `gmail.compose` (drafts only), `documents` and `drive.file`. This produces an `authorized_user` token JSON.
   ```bash
   python -c "from google_auth_oauthlib.flow import InstalledAppFlow as F; c=F.from_client_secrets_file('client.json',['https://www.googleapis.com/auth/calendar.events','https://www.googleapis.com/auth/gmail.compose','https://www.googleapis.com/auth/documents','https://www.googleapis.com/auth/drive.file']).run_local_server(port=0); open('token.json','w').write(c.to_json())"
   ```
3. Store the token as a secret:
   ```bash
   gcloud secrets create GOOGLE_OAUTH_TOKEN --data-file=token.json
   ```
   Then re-run `make deploy`. The script detects the secret, mounts it, and switches the API to `WORKSPACE_MODE=google`.
4. Optional: create a Google Doc named "Timetable Change Log" and set its ID as `CHANGELOG_DOC_ID`. Otherwise the first execution creates the Doc.

## 4. Gemini Enterprise (primary agent path, D-02)
1. In the Google Cloud console, open **Gemini Enterprise → Apps**, then create an app (or open the hackathon app).
2. Under **Data stores**, add an *unstructured* data store named `campus-ops-grounding` and upload the files in `grounding/`: the handbook PDF, the holiday page, the shuttle PDF and `campus_ops_policy.md`.
3. Under **Connectors / Tools**, add a **third-party MCP server**:
   - URL: `<api-url>/mcp`, using the streamable HTTP transport
   - Auth: bearer token, the value of the `MCP_AUTH_TOKEN` secret
   - **VERIFY:** whether your edition supports custom MCP servers and which auth types it accepts. If it only accepts OAuth or IAP, put the API behind IAP and grant the Gemini Enterprise service agent access.
4. Create an agent **Replan**: paste `agents/replan/instructions.md`, attach the MCP tools listed in `agents/replan/config.yaml` and the data store, and turn on user confirmation for `approve_proposal` and `execute_proposal`. Do the same for **Slot Finder**.
5. Test with the `test_prompts` in each `config.yaml`.

## 5. ADK fallback (if step 4 isn't possible in your tenant)
```bash
pip install google-adk
```
```bash
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<GCP_PROJECT> GOOGLE_CLOUD_LOCATION=asia-southeast1 CAMPUS_MCP_URL=<api-url>/mcp MCP_AUTH_TOKEN=<token>
```
```bash
adk web agents
```
To deploy to Vertex AI Agent Engine instead:
```bash
adk deploy agent_engine --project <GCP_PROJECT> --region asia-southeast1 agents/adk_app
```
Record which path you used in `docs/DECISIONS.md` D-02.

## 6. Local development
```bash
make setup
```
```bash
make dev
```
The backend runs on :8000 and the dashboard on :3000. For Firestore instead of JSON files, set `STORE_BACKEND=firestore` before `make dev`; this starts the emulator (gcloud required).
