# Project Migration Guide
**Purpose:** How to move this project to a new machine, new folder, new GitHub account, or new Vercel account — without losing anything.

---

## 1. Moving to a new machine or new folder

Everything you need is in the GitHub repository. The `.env` file (your secrets) lives only on your local machine and is intentionally NOT in GitHub — you'll need to recreate it.

### Steps

```bash
# 1. Install prerequisites on the new machine
#    - Git  (https://git-scm.com/)
#    - Python 3.11  (https://python.org/)
#    - Node.js 18+  (https://nodejs.org/)
#    - (Optional but recommended) VS Code or Cursor IDE

# 2. Clone the repository
git clone https://github.com/Suresh-collab/nifty-options-bot.git
cd nifty-options-bot

# 3. Set up the backend
cd backend
cp .env.example .env
# Open .env in a text editor and fill in your real values:
#   DATABASE_URL, TELEGRAM_BOT_TOKEN, SMTP_*, BROKER_ENCRYPTION_KEY, etc.
#   (See the "Environment Variables Cheatsheet" section below)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 4. Set up the frontend (new terminal tab)
cd frontend
npm install
npm run dev
# → open http://localhost:5173
```

### What you do NOT need to copy manually

| Item | Why |
|---|---|
| All Python source code | In GitHub |
| All React source code | In GitHub |
| All documentation | In GitHub |
| All dependencies list | In `requirements.txt` + `package.json` |
| Database schema | Alembic migrations in `backend/migrations/` |
| `.env` file | Lives only on your machine — recreate from `.env.example` |
| `node_modules/` | Recreated by `npm install` |
| `__pycache__/` | Recreated automatically by Python |
| `paper_trades.db` | SQLite file; lives only locally — this data is NOT in GitHub |

### If you want to preserve paper trade history

The SQLite paper trades database is at `backend/paper_trades.db` (or `/tmp/paper_trades.db` on Vercel). It is gitignored. If you want to keep your trade history when moving machines:

```bash
# On old machine — copy this file to the new machine manually
backend/paper_trades.db

# Place it in the same location on the new machine:
# new-machine:~/nifty-options-bot/backend/paper_trades.db
```

> **Note:** Once paper trades are migrated to Postgres (production readiness item), this file won't matter anymore — all history will be in the database.

---

## 2. Changing your GitHub account

You have two options depending on whether you want to keep the commit history.

### Option A — Transfer ownership (keeps all history, stars, issues)

This is the cleanest approach. GitHub lets you transfer a repo to a different account without losing anything.

1. Go to https://github.com/Suresh-collab/nifty-options-bot
2. Click **Settings** → scroll to the bottom → **Transfer**
3. Enter the new GitHub username and confirm
4. The repo moves to the new account; all existing commit history is preserved
5. Update your local remote:
   ```bash
   git remote set-url origin https://github.com/NEW-USERNAME/nifty-options-bot.git
   git remote -v   # verify the change
   ```

### Option B — Push to a fresh repo on the new account (clean slate)

Use this if you want a brand-new repo without the old account's metadata.

```bash
# 1. Create a new empty repo on the new GitHub account
#    (do NOT initialize with README — keep it empty)
#    Name it: nifty-options-bot  (or any name you prefer)

# 2. Update your local remote to point to the new repo
cd nifty-options-bot
git remote set-url origin https://github.com/NEW-USERNAME/nifty-options-bot.git

# 3. Push everything
git push -u origin main

# Verify: go to https://github.com/NEW-USERNAME/nifty-options-bot
# All code and commit history should be there
```

### After changing GitHub account — update Vercel

Vercel is linked to your GitHub account. After changing accounts, you need to reconnect:

1. Go to https://vercel.com → your project → **Settings** → **Git**
2. Click **Disconnect** and then **Connect Git Repository**
3. Authorize the new GitHub account
4. Select the new repo (`nifty-options-bot`)
5. Vercel will re-deploy from the new repo automatically

---

## 3. Changing your Vercel account

### Option A — Transfer the Vercel project to a new team/account

1. Go to https://vercel.com → your project → **Settings** → **Transfer Project**
2. Enter the destination team or personal account
3. All environment variables, domain settings, and deployment history transfer with it
4. Reconnect to GitHub if prompted (see step above)

### Option B — Deploy from scratch on a new Vercel account

Use this if you're starting completely fresh on a new Vercel account.

```bash
# Prerequisites: npm install -g vercel
```

1. Log in to your new Vercel account at https://vercel.com
2. Click **Add New Project** → **Import Git Repository**
3. Connect your GitHub account (new or existing)
4. Select the `nifty-options-bot` repo
5. Vercel will auto-detect the `vercel.json` config
6. **Before deploying**, set all environment variables (see cheatsheet below):
   - Click **Environment Variables** during setup
   - Add each variable from the list below
7. Click **Deploy**
8. Your app will be live at `https://your-project.vercel.app`

> **Important:** Your old Vercel deployment will keep running until you delete it. The two deployments don't interfere with each other.

---

## 4. Environment Variables Cheatsheet

These are all the values you need to set — in your local `.env` file, in Vercel dashboard, and in any new deployment host (Render/Railway when you migrate the backend).

```bash
# ── REQUIRED ─────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://user:password@host/dbname
# Get this from: Neon (https://neon.tech) — free Postgres
# Format for Neon: postgresql+asyncpg://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require

DATABASE_MIGRATION_URL=postgresql://user:password@host/dbname
# Same as DATABASE_URL but without '+asyncpg' — used by Alembic only

# ── LOGGING ──────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO

# ── FEATURE FLAGS (all OFF by default — SAFETY) ──────────────────────────────
ENABLE_ML_SIGNAL=false
ENABLE_LIVE_BROKER=false
ENABLE_AUTO_EXECUTION=false

# ── ML ────────────────────────────────────────────────────────────────────────
ML_MODEL_VERSION=
# Leave empty to use the latest trained model.

# ── RISK SETTINGS ─────────────────────────────────────────────────────────────
PAPER_TRADING_CAPITAL=100000
DAILY_LOSS_LIMIT_PCT=0.02        # halt when daily loss > 2% of capital
DAILY_PROFIT_TARGET_PCT=0.05     # halt when daily profit > 5% of capital
MAX_OPEN_POSITIONS=5

# ── TELEGRAM ALERTS ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
# How to get these:
#   1. Message @BotFather on Telegram → /newbot → get token
#   2. Message @userinfobot on Telegram → get your chat_id
# Leave blank to disable Telegram alerts.

# ── EMAIL ALERTS ──────────────────────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-app-password   # Gmail: use App Password, not your login password
ALERT_EMAIL_TO=recipient@gmail.com
ALERT_DEDUP_TTL=60
# Leave SMTP_USER blank to disable email alerts.
# Gmail App Password: https://myaccount.google.com/apppasswords

# ── BROKER (Phase 4) ──────────────────────────────────────────────────────────
BROKER_MODE=paper                 # paper (default) or live
BROKER_ENCRYPTION_KEY=            # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
BROKER_SALT=any-random-string-you-choose
# Leave BROKER_ENCRYPTION_KEY blank if you're not testing the broker.
```

### Where to set these

| Environment | Where |
|---|---|
| **Local dev** | `backend/.env` (copy from `backend/.env.example`) |
| **Vercel (frontend + serverless BE)** | Vercel dashboard → Project → Settings → Environment Variables |
| **Render/Railway (long-lived BE)** | Render/Railway dashboard → Service → Environment |
| **GitHub Actions CI** | GitHub repo → Settings → Secrets and variables → Actions |

---

## 5. Forking the repo (for personal copy or experimentation)

If you want a personal copy on GitHub that you control independently:

```bash
# Option A: Use GitHub's Fork button
# 1. Go to https://github.com/Suresh-collab/nifty-options-bot
# 2. Click "Fork" (top right)
# 3. Choose your account as the destination
# 4. Clone YOUR fork:
git clone https://github.com/YOUR-USERNAME/nifty-options-bot.git

# Option B: Create a fresh independent copy (no fork link to original)
# 1. Create a new empty GitHub repo named nifty-options-bot
# 2. Clone the original:
git clone https://github.com/Suresh-collab/nifty-options-bot.git
cd nifty-options-bot
# 3. Point to your new repo:
git remote set-url origin https://github.com/YOUR-USERNAME/nifty-options-bot.git
# 4. Push:
git push -u origin main
```

---

## 6. Quick reference — "What lives where?"

| Data / Asset | Location | Backed up in GitHub? |
|---|---|---|
| All source code | `nifty-options-bot/` folder | ✅ Yes |
| Python dependencies | `backend/requirements.txt` | ✅ Yes |
| Node dependencies | `frontend/package.json` | ✅ Yes (list only; `node_modules/` excluded) |
| Environment secrets | `backend/.env` | ❌ No — you must copy manually |
| Paper trade history (SQLite) | `backend/paper_trades.db` | ❌ No — copy manually if needed |
| OHLCV + ML data (Postgres) | Your Neon/Postgres database | ❌ No — stays in the DB |
| ONNX ML models | `backend/ml/onnx_models/` | ✅ Yes (committed) |
| Documentation | `docs/` | ✅ Yes |
| Vercel env vars | Vercel dashboard | ❌ No — set manually in new account |

---

## 7. Summary — what to do in each scenario

| Scenario | Steps |
|---|---|
| **New machine, same GitHub/Vercel** | Clone repo → fill `.env` → `pip install` + `npm install` → done |
| **New folder on same machine** | `git clone` to new folder → fill `.env` → done |
| **New GitHub account** | Transfer repo OR push to new repo → update `git remote set-url` → reconnect Vercel to new GitHub |
| **New Vercel account** | Transfer project OR import from GitHub on new account → set all env vars in new dashboard |
| **New everything (new machine + new accounts)** | Clone from GitHub → fill `.env` → set up Vercel from scratch → set env vars |
| **Give someone else a copy** | Fork the repo → they clone their fork → they fill their own `.env` |
