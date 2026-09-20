# WhatsApp Setup — Start to Finish

Everything needed to get real WhatsApp messages flowing into the classifier.

Parts A–D use Meta's free test number and take about an hour. Part E is
production and takes days, mostly waiting on Meta.

---

## Part A — Meta app and test number

### 1. Developer account

Go to [developers.facebook.com](https://developers.facebook.com) and log in with
a Facebook account. Click **Get Started** if it is your first time and accept the
developer terms.

### 2. Create the app

**My Apps** → **Create App**

- Use case: **Other**
- Type: **Business**
- Name: anything, e.g. `cod-confirm`
- Business portfolio: create one if you have none

### 3. Add WhatsApp

On the app dashboard, find **WhatsApp** in the product list → **Set up**.

You land on **WhatsApp → API Setup**. Three values live on this page:

| Value | Where | Notes |
|---|---|---|
| **Temporary access token** | top of page | expires every 24 hours |
| **Phone number ID** | under the "From" number | this is NOT the phone number |
| **Test number** | the "From" dropdown | Meta gives you this free |

Copy the token and the Phone number ID somewhere.

### 4. Add your own number as a recipient

**To** dropdown → **Manage phone number list** → **Add phone number**

International format, no `+`, no leading zero:

```
923001234567
```

Meta sends a verification code over WhatsApp. Enter it.

Test mode allows up to 5 recipients. That is plenty for development.

### 5. Send the test message

On the same page, under **Send messages with the API**, click **Send message**.

Your phone receives a "Hello World" WhatsApp message. If it arrives, your token,
phone number ID and recipient are all correct.

Equivalent by hand:

```bash
curl -X POST "https://graph.facebook.com/v21.0/YOUR_PHONE_NUMBER_ID/messages" \
  -H "Authorization: Bearer YOUR_TEMP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messaging_product":"whatsapp","to":"923001234567","type":"template","template":{"name":"hello_world","language":{"code":"en_US"}}}'
```

### 6. Reply from your phone

Reply anything to that message. This opens the **24-hour customer service
window**, during which free-text messages are allowed.

Worth doing once deliberately: before you reply, a free-text send is rejected;
after you reply, it works. That is the single most important rule of this API.

---

## Part B — Run the stack locally

### 7. Start the classifier service

From the project root:

```bash
uvicorn service:app --host 0.0.0.0 --port 8000
```

Check: `curl http://localhost:8000/health`

Leave it running.

### 8. Start n8n

Easiest, no Docker:

```bash
npx n8n
```

Opens on `http://localhost:5678`. Create a local account when prompted.

With Docker instead:

```bash
docker run -it --rm -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

### 9. Import the workflows

In n8n: **Workflows** → **…** menu → **Import from File**

Import both:
- `n8n/01-order-received.json`
- `n8n/02-reply-handler.json`

### 10. Point n8n at the classifier

Open workflow 02 → **Classify Intent** node → check the URL:

| How you run n8n | URL |
|---|---|
| `npx n8n` (on your machine) | `http://localhost:8000/classify` |
| Docker, service on host | `http://host.docker.internal:8000/classify` |

The file ships with the Docker form. Change it if you used npx.

### 11. Set environment variables

n8n reads these through `$env` in the HTTP nodes. Set them **before** starting
n8n, in the same terminal.

PowerShell:

```bash
$env:WA_PHONE_NUMBER_ID="123456789012345"; $env:WA_TOKEN="EAAG..."; $env:SERVICE_TOKEN="any-random-string"; npx n8n
```

Git Bash:

```bash
WA_PHONE_NUMBER_ID=123456789012345 WA_TOKEN=EAAG... SERVICE_TOKEN=any-random-string npx n8n
```

**n8n 2.x blocks `$env` in expressions by default.** The workflows read
`SERVICE_TOKEN`, `WA_TOKEN` and `WA_PHONE_NUMBER_ID` that way, so you must also
set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` or every node using them fails with
`access to env vars denied`:

```
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE="false"; $env:WA_PHONE_NUMBER_ID="..."; $env:WA_TOKEN="EAA..."; $env:SERVICE_TOKEN="dev-secret-123"; n8n start
```

---

## Part C — Let Meta reach n8n

Meta requires a public HTTPS URL. It cannot reach `localhost`.

### 12. Tunnel

```bash
ngrok http 5678
```

Copy the `https://....ngrok-free.app` address it prints. It changes every
restart on the free plan.

### 13. Activate workflow 02

**This matters.** n8n has two webhook URLs per workflow:

| URL | When it works |
|---|---|
| `/webhook-test/whatsapp-reply` | only while you click "Listen for test event" — one request |
| `/webhook/whatsapp-reply` | whenever the workflow is **Active** |

Meta needs the production one, so toggle workflow 02 to **Active** (top right)
before configuring the webhook.

### 14. Configure the webhook in Meta

App dashboard → **WhatsApp** → **Configuration** → **Webhook** → **Edit**

- **Callback URL**: `https://<your-ngrok>.ngrok-free.app/webhook/whatsapp-reply`
- **Verify token**: any string you invent (you do not need it anywhere else yet)

Click **Verify and save**. Meta sends a GET with `hub.challenge`; the
`Webhook Verify (GET)` node echoes it back. If this fails, the workflow is not
active or the ngrok URL is wrong.

### 15. Subscribe to messages

Same page, **Webhook fields** → click **Manage** → tick **messages** → save.

Without this, Meta accepts the webhook but never sends anything to it.

---

## Part D — End to end

### 16. Send yourself a message

From your phone, WhatsApp the test number:

```
ab nahi lena
```

Then check, in order:

1. **n8n → Executions** — a new execution for workflow 02
2. The execution should route through **Mark Cancelled**
3. **Dashboard** at `http://localhost:8000` — "Cancelled before dispatch" goes up, Rs saved increases
4. **Your phone** — a reply arrives confirming the cancellation

If all four happen, the system is live.

### 17. Walk the branches

| Send this | Expect |
|---|---|
| `han bhai confirm hai` | CONFIRM, courier branch |
| `ab nahi lena` | CANCEL, Rs saved rises |
| `abhi nahi baad mein` | RESCHEDULE |
| `acha` | HUMAN inbox |

---

## Part E — Production

Only needed when a real seller goes live.

### 18. Business verification

Meta Business Manager → **Business settings** → **Security Centre** →
**Start verification**. For Pakistan you will typically need an NTN certificate,
a bank statement or utility bill in the business name, and a business website or
social page. Takes days to weeks.

### 19. Permanent token

Temporary tokens die daily. Business settings → **Users** → **System users** →
create one → **Generate new token** → select the app → scopes
`whatsapp_business_messaging` and `whatsapp_business_management`. That token does
not expire.

### 20. Real phone number

**WhatsApp → API Setup** → **Add phone number**.

> **The number must not be registered on WhatsApp or WhatsApp Business already.**
> Most sellers' existing business number is. They either delete it from the app
> first (losing chat history) or use a new number. Expect this objection.

### 21. Message template approval

The confirmation question is business-initiated, so it must be an approved
template.

Business Manager → **WhatsApp Manager** → **Message templates** → **Create**

- Name: `order_confirmation`
- Category: **Utility** (not Marketing — Marketing gets rejected and costs more)
- Language: English, or Urdu if you prefer
- Body, with three variables:

```
Assalam o Alaikum! Your order {{1}} ({{2}}) for Rs {{3}} is cash on delivery.
Should we dispatch it? Reply HAAN to confirm or NAHI to cancel.
```

Approval usually within a day. Utility templates with clear transactional
wording pass easily.

### 22. Costs

Meta bills per 24-hour conversation. Your template opens a paid **utility**
conversation; the customer's reply and your responses inside that window are
included. Check current Pakistan rates at
[Meta's pricing page](https://developers.facebook.com/docs/whatsapp/pricing) —
it is a few rupees per order against roughly Rs 300 saved per prevented failed
delivery. Quote it honestly to clients rather than calling it free.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| "Verify and save" fails | Workflow 02 not Active, or wrong ngrok URL |
| Webhook saved but nothing arrives | `messages` field not subscribed |
| Messages arrive, no execution | Using `/webhook-test/` instead of `/webhook/` |
| `(#131030) recipient not in allowed list` | Number not added under **To** in test mode |
| `(#131047) re-engagement message` | 24-hour window closed — use a template |
| Free-text send rejected | Same. Customer must message you first |
| Token stopped working | Temporary token expired; copy a new one |
| `access to env vars denied` | n8n 2.x blocks `$env` by default - set `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` |
| `$env` empty in n8n | Variables not set before n8n started |
| Classify node connection refused | Wrong host — `localhost` vs `host.docker.internal` |

---

## Security note

The `Webhook Verify (GET)` node echoes `hub.challenge` without checking that
`hub.verify_token` matches what you configured. That is fine for development.
Before production, add an IF node comparing
`{{ $json.query['hub.verify_token'] }}` against your token, and only respond on
a match.
