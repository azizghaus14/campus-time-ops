# Setup from zero (personal Google account, no organiser resources)

Everything below works with **one personal Google account** (e.g. a Gmail address) and the **Google Cloud free trial**. You do not need to buy a domain or Google Workspace. Region: `asia-southeast1`.

## A. Accounts to create (about 10 minutes)
1. **A Google account** for the team. A fresh Gmail is cleanest, e.g. `campustimeops.demo@gmail.com`. All demo emails and invites go to `+` aliases of this inbox, so nothing ever reaches a real person.
2. **Google Cloud free trial** at https://cloud.google.com/free, signed in with that account. You get **US$300 credit for 90 days**. A credit or debit card is needed only to verify identity: you are not charged unless you manually upgrade to a paid account. This project costs a few dollars of credit at most.
3. **A project:** in the console, create a project (e.g. `campus-time-ops`) and note its **Project ID**.
4. **A GitHub account and an empty repository** for the submission.

## B. Deploy (your laptop, about 15 minutes)
```bash
brew install --cask google-cloud-sdk
```
```bash
gcloud auth login
```
```bash
gcloud config set project <PROJECT_ID>
```
```bash
GCP_PROJECT=<PROJECT_ID> WORKSPACE_DEMO_INBOX=<your-demo-gmail> make deploy
```
`scripts/deploy.sh` does the following:
- turns on Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Firestore, Vertex AI, Calendar, Gmail, Docs and Drive
- creates the Firestore database and a least-privilege service account
- generates the `MCP_AUTH_TOKEN` secret
- builds and deploys the **API** and the **web app**, then prints both URLs

Seed a clean demo state:
```bash
BACKEND_URL=<api-url> MCP_AUTH_TOKEN=$(gcloud secrets versions access latest --secret MCP_AUTH_TOKEN) make reset-demo
```
At this point the whole product works online. Calendar, email and change-log outputs are created as files you can open from each executed plan. To make them real Google items, do step C.

## C. Real Google Calendar events, Gmail drafts and a change-log Google Doc (optional, about 15 minutes)
1. In the Cloud console, open **Google Auth Platform**.
   - **Branding:** set an app name and the support email.
   - **Audience:** choose External, leave it in **Testing**, and add your demo Gmail as a **test user**.
2. Under **Clients**, create a client of type **Desktop app**, and download the JSON as `client.json`.
3. Run this once on your laptop, then sign in with the demo Gmail:
   ```bash
   .venv/bin/pip install google-auth-oauthlib
   ```
   ```bash
   .venv/bin/python -c "from google_auth_oauthlib.flow import InstalledAppFlow as F; c=F.from_client_secrets_file('client.json',['https://www.googleapis.com/auth/calendar.events','https://www.googleapis.com/auth/gmail.compose','https://www.googleapis.com/auth/documents','https://www.googleapis.com/auth/drive.file']).run_local_server(port=0); open('token.json','w').write(c.to_json())"
   ```
4. Store the token and redeploy:
   ```bash
   gcloud secrets create GOOGLE_OAUTH_TOKEN --data-file=token.json
   ```
   ```bash
   GCP_PROJECT=<PROJECT_ID> WORKSPACE_DEMO_INBOX=<your-demo-gmail> make deploy
   ```
   The script sees the secret and switches the API to `WORKSPACE_MODE=google`.

⚠️ **Testing-mode tokens expire after 7 days.** Redo step 3 and update the secret before you record the video and before judging:
```bash
gcloud secrets versions add GOOGLE_OAUTH_TOKEN --data-file=token.json
```
Never commit `client.json` or `token.json`. Both are already git-ignored by the `secrets/` convention, so keep them in `secrets/`.

## D. The agents: choose a path
**Path 1: ADK + Gemini on Vertex AI (recommended).** It needs nothing beyond step B. It uses the same project and the free-trial credit.
```bash
.venv/bin/pip install google-adk
```
```bash
gcloud auth application-default login
```
```bash
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<PROJECT_ID> GOOGLE_CLOUD_LOCATION=global CAMPUS_MCP_URL=<api-url>/mcp MCP_AUTH_TOKEN=$(gcloud secrets versions access latest --secret MCP_AUTH_TOKEN)
```
```bash
cd agents && ../.venv/bin/adk web
```
This opens a chat UI with the Replan and Slot Finder agents calling your live MCP server. Set `GEMINI_MODEL` to the newest Gemini available in Vertex AI Model Garden.

**Path 2: Gemini Enterprise (30-day free trial).** This is optional and riskier. Its custom MCP connector:
- uses **OAuth only**
- is **blocked by a managed organization policy** that you must override, which needs the Organization Policy Administrator role; a personal account without a Google Cloud organization may not be able to change it

If you try it:
1. Activate the trial: Cloud console → Gemini Enterprise → create an app → accept the 30-day trial.
2. Create a **Web application** OAuth client with the redirect URI `https://vertexaisearch.cloud.google.com/oauth-redirect`.
3. Redeploy with the OAuth settings:
   ```bash
   MCP_GOOGLE_CLIENT_IDS=<that-client-id> MCP_ALLOWED_EMAILS=<your-demo-gmail> GCP_PROJECT=<PROJECT_ID> WORKSPACE_DEMO_INBOX=<your-demo-gmail> make deploy
   ```
4. In Gemini Enterprise, open **Connected data stores → New data store → Custom MCP Server**. Enter:
   - **MCP server URL:** `<api-url>/mcp`
   - **Authorization URL:** `https://accounts.google.com/o/oauth2/auth`
   - **Token URL:** `https://oauth2.googleapis.com/token`
   - **Client ID and secret** from the Web client in step 2
   - **Scopes:** `openid email`
5. Click **Verify Auth**, create the store, then open **Actions → Reload custom actions → Enable**.
6. Create agents with `agents/replan/instructions.md` and `agents/slot_finder/instructions.md`.

If the org-policy step is blocked, use Path 1 and record which path you used in `docs/DECISIONS.md` (D-02).

## E. Local development
```bash
make setup
```
```bash
make dev
```
The API runs on :8000 and the web app on :3000. If port 3000 is in use, run:
```bash
PORT=3100 make frontend
```
