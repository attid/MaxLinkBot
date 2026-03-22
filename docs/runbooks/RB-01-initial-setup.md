# RB-01: Initial Docker Setup

## Symptoms
First-time deployment. Bot does not start, or starts but users cannot authenticate.

## Diagnosis

1. Check container logs:
   ```bash
   docker compose logs maxlinkbot
   ```

2. Verify all required env vars are set:
   ```bash
   docker compose exec maxlinkbot env | grep -E "TELEGRAM|MAX|ALLOWED"
   ```

3. Verify volume is mounted:
   ```bash
   docker compose exec maxlinkbot ls -la /data/
   ```

## Common Causes

### Missing TELEGRAM_BOT_TOKEN
- Bot does not start, auth errors in logs.
- Fix: Set `TELEGRAM_BOT_TOKEN` in environment or `.env` file.

### Wrong ALLOWED_TELEGRAM_USER_IDS format
- Users are silently ignored.
- Format must be comma-separated integers: `"123456,789012"`
- No spaces, no quotes in the value itself.

### Wrong MAX_BASE_URL
- Auth errors when user attempts `/start`.
- Fix: Verify Pumax API URL with your MAX administrator.

### SQLite volume not persisted
- Database resets on every restart.
- Fix: Ensure `maxlinkbot-data` volume is created and mounted correctly.

## Resolution

1. Set all required env vars.
2. Deploy:
   ```bash
   docker compose up -d --build
   ```
3. Verify container is running:
   ```bash
   docker compose ps
   ```
4. Check logs for startup errors:
   ```bash
   docker compose logs -f maxlinkbot
   ```
