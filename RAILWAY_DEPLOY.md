# 🚂 Railway Deployment Guide

## Quick Deploy (3 minutes)

### Option 1: Web Interface (Easiest)

1. **Go to Railway:** https://railway.app
   - Sign up with GitHub account

2. **Create New Project:**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose `marcorosata/FITBIT-AGENT`
   - Railway auto-detects configuration

3. **Set Environment Variables:**
   Click "Variables" tab and add:
   ```
   OPENAI_API_KEY=sk-your-key-here
   FITBIT_CLIENT_ID=your_fitbit_client_id
   FITBIT_CLIENT_SECRET=your_fitbit_secret
   ```

4. **Deploy:**
   - Railway builds automatically
   - Wait for deployment (~2-3 minutes)
   - Get your public URL: `https://wearable-agent-production-xxxx.up.railway.app`

5. **Update Flutter App:**
   - Open Flutter app → Settings
   - Set Server URL to your Railway URL
   - Save and reconnect

---

### Option 2: Railway CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Link to repo
railway link

# Set environment variables
railway variables set OPENAI_API_KEY=sk-...
railway variables set FITBIT_CLIENT_ID=...
railway variables set FITBIT_CLIENT_SECRET=...

# Deploy
railway up

# Get URL
railway domain
```

---

## Environment Variables Reference

### **Required:**
```env
# Railway automatically sets:
PORT=8000                    # Railway provides this

# You must set:
OPENAI_API_KEY=sk-...        # OpenAI API key for agent
```

### **Optional (Fitbit Integration):**
```env
FITBIT_CLIENT_ID=23RXXXX
FITBIT_CLIENT_SECRET=abc123...
FITBIT_REDIRECT_URI=https://your-app.railway.app/auth/fitbit/callback
FITBIT_RATE_LIMIT_PER_HOUR=150
```

### **Optional (Notifications):**
```env
WEBHOOK_URL=https://hooks.slack.com/...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_app_password
NOTIFICATION_EMAIL_FROM=alerts@yourdomain.com
```

---

## Database Options

### Option A: SQLite (Default - Ephemeral)
Railway will use SQLite by default. **Note:** Data resets on each deploy.

```env
# No configuration needed - uses local file
DATABASE_URL=sqlite+aiosqlite:///data/wearable_agent.db
```

### Option B: PostgreSQL (Persistent - Recommended)

1. **Add PostgreSQL plugin:**
   - Railway dashboard → "New" → "Database" → "PostgreSQL"
   - Railway auto-creates `DATABASE_URL` variable

2. **Update your .env (for local dev):**
   ```env
   DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/railway
   ```

3. **Install asyncpg:**
   ```bash
   pip install asyncpg
   # Add to pyproject.toml: asyncpg
   ```

4. **Re-deploy:**
   ```bash
   git add pyproject.toml
   git commit -m "Add PostgreSQL support"
   git push origin main
   ```

---

## Health Checks

Once deployed, test your endpoints:

```bash
# Health check
curl https://your-app.railway.app/health

# API docs (OpenAPI)
open https://your-app.railway.app/docs
```

---

## Monitoring & Logs

### View Logs:
- Railway dashboard → "Deployments" → Click latest build → "Logs"

### Common Issues:

**❌ "Application failed to respond"**
- Check logs for Python errors
- Verify PORT environment variable
- Ensure all dependencies installed

**❌ "Module not found"**
- Add missing package to `pyproject.toml`
- Rebuild: `git commit --allow-empty -m "Rebuild"`

**❌ "Database error"**
- If using PostgreSQL, verify DATABASE_URL
- Check asyncpg is installed

---

## Custom Domain (Optional)

1. Railway dashboard → "Settings" → "Domains"
2. Click "Generate Domain" (free)
   - Or add custom domain: `api.yourdomain.com`
3. Update DNS records if using custom domain

---

## Scaling & Performance

- **Free Tier:** 500 hours/month, sleeps after inactivity
- **Hobby Plan ($5/mo):** Always on, more resources
- **Auto-scaling:** Railway handles load automatically

---

## Security Checklist

✅ Set strong `API_SECRET_KEY` in environment variables
✅ Use HTTPS only (Railway provides automatic SSL)
✅ Keep `.env` file out of git (already in `.gitignore`)
✅ Rotate Fitbit tokens regularly
✅ Enable Railway's built-in DDoS protection

---

## Next Steps

1. **Connect Flutter App:**
   ```dart
   // In Settings screen
   baseUrl = "https://your-app.railway.app"
   ```

2. **Test WebSocket:**
   ```bash
   wscat -c wss://your-app.railway.app/ws/stream
   ```

3. **Monitor usage:**
   - Railway dashboard shows metrics
   - Set up alerts for errors

---

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- GitHub Issues: https://github.com/marcorosata/FITBIT-AGENT/issues

---

**Your app is now live! 🎉**

Share your Railway URL with Flutter app users to start collecting data.
