# Whiteout Bot - VPS Docker Runbook (Turnkey)

This runbook assumes a fresh Ubuntu VPS and Docker hosting.

## 1) VPS Plan Choice
- Recommended: LS-3 (3GB RAM) for auto gift redemption + OCR.

## 2) Install Docker (Ubuntu)
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 3) Deploy the bot
```bash
sudo mkdir -p /opt/wos-bot
cd /opt/wos-bot
```

Copy the repo here (SFTP or git), then:
```bash
cp .env.example .env
```

Edit `.env` and set:
- `DISCORD_BOT_TOKEN=...`

Start the container:
```bash
docker compose up -d --build
docker logs -f wos-discord-bot
```

Data is stored under:
- `./data/db` (sqlite databases)
- `./data/log` (logs)
- `./data/backups` (automatic backups)
- `./data/captcha_images` (optional captcha images)

## 4) Discord setup (first time)
1. Invite the bot with Administrator permissions.
2. Run `/settings` to create the first Global Admin.
3. Configure:
   - Gift Codes: Channel Management + Auto Redemption + CAPTCHA Settings (enable solver)
   - Registration: enable self-registration
   - ID Channel: create channel for ID verification
   - Notifications: set timezone to UTC and create event reminders

## 5) Recommended personalization
- Alliance names and member lists
- Gift redemption order (Redemption Priority)
- Attendance report type (text vs matplotlib)

## 6) Operational notes
- Auto-update is OFF by default in Docker (`UPDATE=0` in compose).
- Updates are blocked unless you set `WOS_ALLOW_UNSIGNED_UPDATE=1` or provide `WOS_UPDATE_SHA256`.
- SSL verification is ON by default. If the host has TLS issues, set `WOS_INSECURE_SSL=1` in `.env`.
