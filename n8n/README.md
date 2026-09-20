# n8n Workflows — COD Order Confirmation

Two workflows. Import both into n8n via **Workflows → Import from File**.

| File | Trigger | Does |
|---|---|---|
| `01-order-received.json` | New order webhook | Sends the WhatsApp confirmation question |
| `02-reply-handler.json` | Customer's WhatsApp reply | Classifies it and routes the order |

## Flow

```
01:  order webhook -> normalize -> ask customer on WhatsApp

02:  WhatsApp reply -> parse -> look up order -> POST /classify
                                                      |
                              +-----------+-----------+-----------+
                              |           |           |           |
                          CONFIRM      CANCEL    RESCHEDULE     HUMAN
                              |           |           |           |
                        book courier  mark        queue       human
                              |       cancelled   retry +1d    inbox
                              +-----------+-----------+-----------+
                                          |
                                 send WhatsApp reply
```

`HUMAN` is the fallback output, so **anything the switch does not explicitly
match ends up in front of a person.** Questions, address changes, order changes
and low-confidence replies all land there. That default is deliberate: a new
intent added later fails safe rather than silently booking a courier.

## Setup

### 1. Run the classifier service

From the project root:

```
uvicorn service:app --host 0.0.0.0 --port 8000
```

Check it: `curl http://localhost:8000/health`

### 2. Point n8n at it

The `Classify Intent` node calls `http://host.docker.internal:8000/classify`,
which is how a container reaches a service on the host.

- **n8n in Docker, service on host** — leave as is
- **n8n installed directly (npx/npm)** — change to `http://localhost:8000/classify`
- **Both in Docker Compose** — use the service name, e.g. `http://classifier:8000/classify`

### 3. Environment variables

Set these where n8n runs:

| Variable | Value |
|---|---|
| `WA_PHONE_NUMBER_ID` | From Meta WhatsApp Business setup |
| `WA_TOKEN` | Meta access token |
| `SERVICE_TOKEN` | Any random string; set the same one for the service |

Set `SERVICE_TOKEN` on the service too, so only n8n can drive your order
pipeline:

```
set SERVICE_TOKEN=some-long-random-string
```

### 4. Meta webhook

Point the WhatsApp webhook at the `02` workflow's production URL:
`https://<your-n8n-host>/webhook/whatsapp-reply`

For local development, expose n8n with a tunnel (`ngrok http 5678`) — Meta
requires a public HTTPS endpoint.

## Stubs to replace before production

Two `Code` nodes are placeholders, both marked `STUB` in the code:

- **Look Up Order** — returns a fake order. Replace with a Postgres node or an
  HTTP call to the seller's order system, keyed on `customer_phone`.
- **Book Courier** — a NoOp. Replace with the courier's API (PostEx, Leopards,
  TCS all have REST APIs).

Everything else runs as-is, which is enough to record a demo.

## Testing without WhatsApp

You do not need Meta approval to demo this. Post a fake Meta payload straight at
the `02` webhook:

```
curl -X POST http://localhost:5678/webhook-test/whatsapp-reply ^
  -H "Content-Type: application/json" ^
  -d "{\"entry\":[{\"changes\":[{\"value\":{\"messages\":[{\"from\":\"923001234567\",\"id\":\"wamid.TEST\",\"type\":\"text\",\"text\":{\"body\":\"ab nahi lena\"}}]}}]}]}"
```

Change the `body` value to walk every branch:

| Reply | Expected route |
|---|---|
| `han bhai confirm hai` | CONFIRM → book courier |
| `ab nahi lena` | CANCEL → no dispatch |
| `kal bhej dena` | RESCHEDULE → retry in 24h |
| `address change karna hai` | HUMAN |
| `acha` | HUMAN (ambiguous) |

That table is also your demo script — five messages, five different outcomes,
one minute of video.

## Note on the WhatsApp send nodes

They post to the Meta Cloud API directly via HTTP Request rather than using a
WhatsApp credential node, so the workflow imports cleanly without credentials
configured. Swap in n8n's WhatsApp node later if you prefer credential storage
over environment variables.
