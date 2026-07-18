# Deploying ConstructX AI to a Linux VPS

This guide deploys the app to a Linux server (Ubuntu/Debian) for internal / IP
access at `http://YOUR_SERVER_IP:8000`. No domain or HTTPS required.

---

## 0. What you need
- A Linux VPS (Ubuntu 22.04+/Debian 12+ recommended) with **SSH access** and sudo.
- The server's public IP address.
- ~2 GB RAM minimum (scikit-learn training needs a little headroom).

---

## 1. Install Docker on the server
SSH in, then:

```bash
# Install Docker Engine + Compose plugin (official convenience script)
curl -fsSL https://get.docker.com | sudo sh

# Let your user run docker without sudo (log out/in afterwards)
sudo usermod -aG docker $USER

# Verify
docker --version
docker compose version
```

---

## 2. Copy the project to the server
From your **local machine**, from the folder that contains `constructx-demo/`:

```bash
# Option A — scp the whole folder
scp -r constructx-demo youruser@YOUR_SERVER_IP:~/

# Option B — if it's in a git repo
# ssh in, then: git clone <your-repo-url>
```

Then SSH into the server and enter the folder:
```bash
ssh youruser@YOUR_SERVER_IP
cd ~/constructx-demo
```

---

## 3. Set the database password
```bash
cp .env.example .env
nano .env          # set POSTGRES_PASSWORD to a long random value, save & exit
```

Generate a strong one quickly:
```bash
openssl rand -base64 24
```

---

## 4. Build & start
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
First run takes a few minutes (installs scikit-learn, builds the image). On
startup the app creates the tables, seeds the demo data, and trains the 8 models.

Check it's healthy:
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api   # Ctrl+C to stop tailing
# look for: "[startup] ConstructX AI demo ready"
```

---

## 5. Open the firewall for port 8000
Ubuntu (ufw):
```bash
sudo ufw allow 8000/tcp
sudo ufw enable          # if not already enabled (make sure 22/SSH is allowed first!)
sudo ufw status
```
> The PostgreSQL port (5432) is intentionally **not** exposed — the database is
> only reachable by the api container, never from the internet.

Now open **`http://YOUR_SERVER_IP:8000`** in a browser.

---

## Everyday operations

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f api

# Restart
docker compose -f docker-compose.prod.yml restart api

# Stop everything
docker compose -f docker-compose.prod.yml down

# Update after code changes (re-pull/scp, then):
docker compose -f docker-compose.prod.yml up -d --build

# Back up the database
docker exec constructx_db pg_dump -U constructx constructx > backup_$(date +%F).sql

# Restore a backup
cat backup.sql | docker exec -i constructx_db psql -U constructx -d constructx
```

---

## ⚠️ Security notes (read this)

1. **There is no login/authentication yet.** Anyone who can reach
   `http://SERVER_IP:8000` can view and edit the data. For internal use, restrict
   access with the firewall to trusted IPs, e.g.:
   ```bash
   sudo ufw allow from YOUR_OFFICE_IP to any port 8000 proto tcp
   sudo ufw deny 8000/tcp
   ```
   or put it behind a VPN / SSH tunnel.

2. **The data is a demo dataset.** Predictions are trained on synthetic data —
   see the README caveat. Use real historical data before relying on outputs.

3. **To add a domain + HTTPS later**, put a reverse proxy (Caddy or Nginx) in
   front of port 8000. Ask and I'll provide that config.

---

## Troubleshooting
- **`POSTGRES_PASSWORD must be set`** → you didn't create `.env` (step 3).
- **Can't reach the site** → check `ufw status` (port 8000 open?) and
  `docker compose -f docker-compose.prod.yml ps` (both containers `Up`?).
- **api keeps restarting** → `docker compose -f docker-compose.prod.yml logs api`
  to see the error (usually the DB wasn't ready — it retries automatically).
- **Out of memory during build** → add swap:
  `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`
