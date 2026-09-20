# Deploying for a Client

The local setup is for building and demoing. **Do not hand it to a seller.** It
needs a laptop switched on, three terminals, a tunnel URL that changes daily and
a token that expires every 24 hours.

A client's system must run unattended. This is how.

---

## What it costs

| | Monthly |
|---|---|
| VPS (Hetzner CX22, Contabo, DigitalOcean) | ~$5 |
| Domain | ~$1 (≈$10/year) |
| WhatsApp conversations (billed by Meta to the client) | a few rupees per order |
| **Total infrastructure** | **~$6/month** |

Charge a maintenance fee well above that. You are being paid to keep it working,
not to resell a server.

---

## 1. Get a server

Any VPS with 2GB RAM. Ubuntu 24.04.

Install Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

## 2. Point two subdomains at it

Create two A records pointing at the server's IP:

```
n8n.yourclient.com    ->  203.0.113.10
dash.yourclient.com   ->  203.0.113.10
```

Wait for DNS to propagate before continuing, or Caddy cannot get certificates.

## 3. Copy the project up

```bash
git clone https://github.com/waqaskhan0/whatsapp-cod-agent.git
cd whatsapp-cod-agent/deploy
cp .env.example .env
nano .env
```

Fill in every value. For the dashboard password:

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'the-password'
```

## 4. Get a permanent WhatsApp token

**Do not use the 24-hour token from the app dashboard.** It expires overnight and
the client's system stops silently.

Meta Business settings → **Users** → **System users** → create one →
**Generate new token** → select the app → scopes `whatsapp_business_messaging`
and `whatsapp_business_management`. That token does not expire.

## 5. Start it

```bash
docker compose up -d
```

Check:

```bash
docker compose ps
docker compose logs -f
```

Caddy will fetch HTTPS certificates on first run. Give it a minute.

## 6. Import the workflows

Open `https://n8n.yourclient.com`, create the owner account, and import both
files from `n8n/`.

In **Classify Intent**, set the URL to:

```
http://classifier:8000/classify
```

That is the container name on the internal Docker network — not `localhost`,
which inside the n8n container means the n8n container itself.

Publish both workflows.

## 7. Point Meta at it

Callback URL — permanent this time, no ngrok:

```
https://n8n.yourclient.com/webhook/whatsapp-reply
```

Then, **and this is the step everyone misses**, subscribe the app to the
WhatsApp Business Account:

```bash
curl -X POST "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" \
  -H "Authorization: Bearer <TOKEN>"
```

Verify your app id is actually in the list:

```bash
curl "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" \
  -H "Authorization: Bearer <TOKEN>"
```

A test WABA is subscribed by default to Meta's own `WA DevX Webhook Events 1P
App`, so this call returns data even when your app is missing. **Check for your
app id specifically.** Without it, everything looks configured and no message is
ever delivered.

## 8. Confirm it survives a reboot

```bash
sudo reboot
```

Wait a minute, then check the dashboard is back. `restart: unless-stopped` should
bring all three containers up on its own. **Test this before handover** — it is
the whole difference between a product and a demo.

---

## What the client sees

- `https://dash.yourclient.com` — their savings dashboard, password protected
- Nothing else. They never see n8n, a terminal, or a log file.

## What you monitor

```bash
docker compose logs -f classifier   # classification decisions
docker compose logs -f n8n          # workflow runs
docker compose ps                   # health
```

Set up an uptime check (UptimeRobot is free) on `https://dash.yourclient.com`.
**You want to know the client's system is down before they do.**

---

## Ongoing jobs

| Job | When | Why |
|---|---|---|
| Check the human inbox is being cleared | weekly | escalations piling up means staff have stopped reading them |
| Review misclassifications | monthly | real replies drift from what you tuned on |
| Retune the prompt on real data | monthly | this is what the retainer pays for |
| Confirm the courier API still works | monthly | they change without notice |
| Renew nothing | — | Caddy renews certificates, the System User token does not expire |

## Backups

The decision history lives in the `classifier_data` volume:

```bash
docker run --rm -v deploy_classifier_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/cod-backup-$(date +%F).tar.gz /data
```

Run it on a cron. A seller's order history disappearing is not recoverable, and
it is your fault if it happens.

---

## Handover checklist

- [ ] Reboot test passed
- [ ] Uptime monitoring in place
- [ ] Backups scheduled and one restore tested
- [ ] Client has the dashboard URL and password
- [ ] Client knows how to clear the human inbox
- [ ] Meta billing is on the client's payment method, not yours
- [ ] `subscribed_apps` verified to contain the app id
- [ ] System User token in use, not a temporary one
- [ ] Client knows what to do if a message is misread (tell you, so you can retune)
