# Credentials & Setup Checklist

> Last updated: 2026-05-02
> Status key: ✅ Done · ⬜ Not yet · ⚠️ Partial

---

## 1. Neon PostgreSQL (database)

| Variable | Status | Value / Notes |
|---|---|---|
| `DATABASE_URL` | ✅ Done | Neon pooler URL configured |
| `DATABASE_MIGRATION_URL` | ✅ Done | Neon direct URL configured |

**Where to manage:** [console.neon.tech](https://console.neon.tech) → your project → Connection Details

---

## 2. Anthropic API (AI signal explanations)

| Variable | Status | Value / Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Done | `sk-ant-api03-...` key set in `.env` |

**Where to manage:** [console.anthropic.com](https://console.anthropic.com) → API Keys

---

## 3. Telegram Bot (trade alerts)

| Variable | Status | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ⬜ Not yet | Get from @BotFather |
| `TELEGRAM_CHAT_ID` | ⬜ Not yet | Get after creating bot (see steps below) |

**How to set up:**
1. Open Telegram → search **@BotFather** → send `/newbot`
2. Follow prompts → BotFather returns a token like `1234567890:ABCdef...`
3. Set `TELEGRAM_BOT_TOKEN=<that token>` in `.env`
4. Send any message to your new bot
5. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser
6. Find `result[0].message.chat.id` → set `TELEGRAM_CHAT_ID=<that number>`

**What it unlocks:** trade entry/exit alerts, kill-switch notifications, SL-hit warnings

---

## 4. Email / SMTP (daily P&L summary)

| Variable | Status | Notes |
|---|---|---|
| `SMTP_HOST` | ✅ Done | `smtp.gmail.com` (pre-filled in `.env.example`) |
| `SMTP_PORT` | ✅ Done | `587` (pre-filled) |
| `SMTP_USER` | ⬜ Not yet | Your Gmail address |
| `SMTP_PASSWORD` | ⬜ Not yet | Gmail App Password (NOT your login password) |
| `ALERT_EMAIL_TO` | ⬜ Not yet | Recipient address (can be same as SMTP_USER) |
| `ALERT_DEDUP_TTL` | ✅ Default | `60` seconds — change only if needed |

**How to get Gmail App Password:**
1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** (required)
3. Search for **App Passwords** → select app: "Mail", device: "Other" → name it "NiftyBot"
4. Copy the 16-character password → set as `SMTP_PASSWORD`

**What it unlocks:** end-of-day HTML P&L summary email, critical event alerts

---

## 5. Zerodha Kite Connect (live broker)

> ⚠️ Only needed when you're ready to flip `ENABLE_LIVE_BROKER=true`. Paper trading works without this.

| Variable | Status | Notes |
|---|---|---|
| `KITE_API_KEY` | ⬜ Not yet | From Kite Developer Console |
| `KITE_ACCESS_TOKEN` | ⬜ Not yet | Regenerated every trading day via OAuth |
| `BROKER_MODE` | ✅ Default | `paper` — change to `live` only after full validation |
| `BROKER_ENCRYPTION_KEY` | ⬜ Not yet | Generate locally (see command below) |
| `BROKER_SALT` | ⬜ Not yet | Any non-empty string you choose |

**How to get Kite credentials:**
1. Sign up at [kite.trade/signup](https://kite.trade/signup) with your Zerodha account
2. Go to **My Apps → Create App** → fill app name + redirect URL
3. Copy `API Key` and `API Secret` from the app page
4. Set `KITE_API_KEY=<api key>` in `.env`
5. Each morning, generate a fresh access token:
   - Visit `https://kite.trade/connect/login?api_key=YOUR_KEY&v=3`
   - Login → authorize → copy the `request_token` from the redirect URL
   - Exchange it via the `POST /api/broker/api-keys` endpoint (Phase 4)

**How to generate Fernet encryption key (run once locally):**
```bash
cd backend
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output → set as `BROKER_ENCRYPTION_KEY`. For `BROKER_SALT` use any memorable string, e.g. `niftybot-prod-2026`.

> Cost: Kite Connect API access costs ₹2,000/month for live trading accounts.

**What it unlocks:** live order placement, position tracking, real-time fills via Zerodha

---

## 6. Feature flags (flip after validation)

| Variable | Current | Flip when |
|---|---|---|
| `ENABLE_ML_SIGNAL` | ⬜ `false` | Phase 2 shadow stats show ≥ 70% agreement rate over 1 week |
| `ENABLE_LIVE_BROKER` | ⬜ `false` | After paper trading validated + Kite credentials set |
| `ENABLE_AUTO_EXECUTION` | ⬜ `false` | After live broker tested manually for ≥ 1 week |

---

## 7. GitHub Actions secrets (for CI)

> Only needed if you push to GitHub and want CI to run tests against the real database.

| Secret name | Status | Value |
|---|---|---|
| `DATABASE_URL` | ⬜ Not yet | Same Neon pooler URL from `.env` |
| `ANTHROPIC_API_KEY` | ⬜ Not yet | Same key from `.env` |

**Where to add:** GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

---

## 8. Vercel environment variables (for production deploy)

> Only needed when deploying to Vercel. The frontend + serverless backend are already wired.

**Where to add:** [vercel.com](https://vercel.com) → your project → **Settings → Environment Variables**

| Variable | Status |
|---|---|
| `DATABASE_URL` | ⬜ Add to Vercel |
| `DATABASE_MIGRATION_URL` | ⬜ Add to Vercel |
| `ANTHROPIC_API_KEY` | ⬜ Add to Vercel |
| `TELEGRAM_BOT_TOKEN` | ⬜ Add to Vercel (after getting it) |
| `TELEGRAM_CHAT_ID` | ⬜ Add to Vercel (after getting it) |
| `SMTP_USER` | ⬜ Add to Vercel (after getting it) |
| `SMTP_PASSWORD` | ⬜ Add to Vercel (after getting it) |
| `ALERT_EMAIL_TO` | ⬜ Add to Vercel (after getting it) |
| `BROKER_ENCRYPTION_KEY` | ⬜ Add to Vercel (after generating) |
| `BROKER_SALT` | ⬜ Add to Vercel (after setting) |
| `KITE_API_KEY` | ⬜ Add to Vercel (when ready for live) |
| `LOG_LEVEL` | ⬜ Add to Vercel (set to `WARNING` for prod) |
| `APP_ENV` | ⬜ Add to Vercel (set to `production`) |
| Feature flags | ⬜ Add all 3 flags (default `false`) |

---

## Summary — what to do next

| Priority | Action | Time needed |
|---|---|---|
| 1 | Create Telegram bot via @BotFather + get chat ID | 5 min |
| 2 | Generate Gmail App Password + fill SMTP vars in `.env` | 5 min |
| 3 | Generate `BROKER_ENCRYPTION_KEY` + set `BROKER_SALT` in `.env` | 2 min |
| 4 | Add GitHub secrets for CI | 5 min |
| 5 | Zerodha Kite Connect developer account (₹2,000/month) | When ready for live |
| 6 | Add all vars to Vercel before production deploy | When ready to deploy |
