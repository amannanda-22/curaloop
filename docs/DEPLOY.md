# Run it, ship it

## A. On your laptop (2 commands)
```bash
pip install -r backend/requirements.txt
python run.py                 # http://localhost:8000  (first start seeds the synthetic cohort)
```
Reset the data: `python run.py --reset`. Needs Python 3.10+; Node is only needed to rebuild the UI (`cd frontend && npm install && npm run build`).

## B. Docker (app + PostgreSQL)
```bash
docker compose up --build     # http://localhost:8000
```

## C. Public link for the jury: Render (API + database) and Vercel (UI)
Why two hosts: the API needs SciPy, pandas and a real database, which do not fit Vercel's serverless limits. Render runs the
Docker image; Vercel serves the React app and forwards `/api/*` to Render.

**1. Render (about 5 minutes)**
1. render.com, New, **Blueprint**, pick the `curaloop` repo. `render.yaml` creates the web service and a free Postgres.
2. Wait for the first deploy (the first start seeds the data). Open `https://<service>.onrender.com/api/health`; it should say `"status":"ok"`.
3. Note the service URL. Free services sleep after inactivity, so open the link once a few minutes before any demo.

**2. Vercel (about 3 minutes)**
1. In `frontend/vercel.json` replace `curaloop-api.onrender.com` with your Render host name, commit, push.
2. vercel.com, Add New, Project, import the repo, set **Root Directory = `frontend`**. Framework Vite is detected. Deploy.
3. Open the Vercel URL: UI loads and `/api/...` calls reach Render.

Use the Vercel URL as the "Prototype / Deployment link" in the form, and keep the Render URL as backup.

## D. Pilot mode (real staff, no demo tools)
Set these environment variables on the host:
```
AUTH_MODE=secure
SECRET_KEY=<python -c "import secrets;print(secrets.token_hex(32))">
CURALOOP_PW_COORDINATOR=...   CURALOOP_PW_FACILITY=...   CURALOOP_PW_MANAGER=...
WHATSAPP_VERIFY_TOKEN=...     WHATSAPP_APP_SECRET=...      # optional, for the WhatsApp Cloud API
```
The login screen appears, the role switcher disappears, the time machine and reset are disabled, and the server refuses to start without the secrets.

## E. Push to GitHub
```bash
cd curaloop
git init -b main
git add .
git commit -m "CuraLoop: screening-to-care closed-loop platform"
git remote add origin https://github.com/amannanda-22/curaloop.git
git push -u origin main
```
