# Nceda Ledger

A digital credit ledger for spaza shops and small merchants. Merchants log what
customers owe; customers consent and pay through a simulated phone portal
(WhatsApp consent flow + MoMo payment).

- **Backend:** FastAPI + SQLModel, PostgreSQL (Neon) in production
- **Frontend:** single file, `NcedaLedger-Final.html` (no build step)

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then put your real DATABASE_URL in .env
uvicorn main:app --reload   # API on http://localhost:8000 (docs at /docs)
```

Serve or open `NcedaLedger-Final.html` in a browser. It talks to
`http://localhost:8000` by default. To point it elsewhere, run this once in the
browser console:

```js
localStorage.setItem('nceda_api_base', 'https://your-api.example.com')
```

## Configuration (`.env`)

| Variable          | Purpose                                                              |
| ----------------- | -------------------------------------------------------------------- |
| `DATABASE_URL`    | Required. Postgres connection string.                                |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins. Defaults to `*`; set it in production. |
| `SQL_ECHO`        | `1` logs every SQL statement (dev only).                             |

**Never commit `.env`.** It is git-ignored; use `.env.example` as the template.

## API

| Method | Path                           | Description                                           |
| ------ | ------------------------------ | ----------------------------------------------------- |
| GET    | `/health`                      | Liveness and DB connectivity                          |
| GET    | `/api/ledger`                  | Debts with customer info. `?status=`, `?limit=`, `?offset=` |
| POST   | `/api/debts`                   | Log a debt (creates the customer on first use)        |
| PATCH  | `/api/debts/{id}/status`       | `?status=PENDING\|ACTIVE\|OVERDUE\|SETTLED`           |

Validation: national ID must be 13 digits, amount must be positive, phone must
be 9-15 digits. An existing ID submitted with a different name is rejected. A
settled debt cannot be reopened.

## Tests

```bash
pytest
```

Tests run against an in-memory SQLite database, so they never touch Neon.

## Known gaps / next steps

- **No authentication.** Anyone who can reach the API can read the ledger and
  change statuses. Add merchant login (and tie debts to `merchant_id`) before
  real use.
- The customer consent and payment flows are simulated in the UI; the status
  endpoint is not yet protected by a customer-side token.
- National IDs are personal information under POPIA: add access controls,
  retention rules and consider encrypting the column at rest.
- No database migrations yet (tables are created on startup). Add Alembic
  before changing the schema in production.
