# Standalone Browser Web App Guide (Zero Electron)

**Daily Stock Analysis (DSA)** runs natively as an independent, installable **Progressive Web App (PWA)** directly inside Chrome, Edge, Safari, or Firefox — with zero Electron desktop wrapper overhead.

---

## 1. Local Standalone Browser App (Windows — 1-Click)

From the repository root, use `dsa-web.cmd` (or `scripts/windows/web_app.ps1`):

```powershell
# Start FastAPI silently (if not running) and open borderless Edge/Chrome App Mode
.\dsa-web.cmd

# Open in a normal browser tab instead of borderless App Mode
.\dsa-web.cmd -Tab

# Create a Windows Desktop shortcut ("DSA Web App") — replaces the Electron desktop app
.\dsa-web.cmd -CreateShortcut

# Register background Web App server to start automatically at Windows logon
.\dsa-web.cmd -RegisterServer

# Check live server & autostart status / Stop background server
.\dsa-web.cmd -Status
.\dsa-web.cmd -Stop
```

### Install as a Browser PWA (Chrome / Edge)
1. Open `http://127.0.0.1:8000/discover` in Chrome or Edge.
2. Click **`Uygulama Yükle`** in the top status bar (or the install icon in the browser address bar).
3. DSA installs as a lightweight standalone browser application with its own taskbar/start-menu icon and instant startup.

---

## 2. Mobile / Tablet / LAN Wi-Fi Access

```powershell
# Bind to 0.0.0.0 and print your local Wi-Fi URL (e.g. http://192.168.x.x:8000/discover)
.\dsa-web.cmd -Lan
```

> **Security Tip:** Before exposing the app on a shared Wi-Fi network or public URL, enable **`ADMIN_AUTH_ENABLED=true`** (from `/settings` or `.env`) and set an administrator password.

---

## 3. Cloud / Self-Hosted Web Deployment (Desktop-Free)

### Option A · Single-Container Docker Web App (Recommended)
Everything (compiled React SPA + PWA assets + FastAPI API) runs from one container:
```bash
docker compose -f docker/docker-compose.yml up -d server
```
Set `API_PORT=8000`, `ADMIN_AUTH_ENABLED=true`, and mount `./data` for persistent SQLite + `data/strategy_paper/` ledgers.

### Option B · Split Frontend (Vercel / Netlify / Cloudflare Pages) + Remote FastAPI Backend
1. **Frontend (`apps/dsa-web`):**
   - Vercel uses `apps/dsa-web/vercel.json` automatically (SPA rewrites + PWA headers).
   - Netlify / Cloudflare Pages uses `apps/dsa-web/public/_redirects` automatically.
   - Set environment variable `VITE_API_URL=https://api.your-domain.example` (see `apps/dsa-web/.env.example`).
2. **Backend (VPS / Render / Railway / Docker):**
   - Set `CORS_ORIGINS=https://your-web-app.vercel.app` and `ADMIN_AUTH_ENABLED=true` in `.env`.
   - Start with `uvicorn server:app --host 0.0.0.0 --port 8000`.
