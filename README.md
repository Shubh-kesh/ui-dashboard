# ui-dashboard

LivePhoto **KYC dashboard**: transaction volume over time, per-stage status,
latency and fraud analysis over the `LIVE_PHOTO_LOGS` catalog.

It replaces the original Streamlit monolith (kept under `legacy/streamlit/`) with:

| Layer    | Stack                                                             |
| -------- | ----------------------------------------------------------------- |
| Backend  | FastAPI + pandas + pyodbc (direct MSSQL, no uidb proxy)           |
| Frontend | Vite + React + TypeScript + Tailwind + TanStack Query + Plotly    |
| Local DB | Azure SQL Edge container (`aikyc-mssql`) with the full schema      |

## Data model

Reads are split across two tables in the same database:

| Table                      | Contents                                   |
| -------------------------- | ------------------------------------------ |
| `LIVE_PHOTO_LOGS`          | recent data (last `LIVE_WINDOW_DAYS`, default 7 days) |
| `LIVE_PHOTO_LOGS_ARCHIVE`  | older data                                 |

The UI has a **Dataset** switcher (Live / Archive). When the chosen start date
predates the live window the UI auto-selects Archive; the switcher always
overrides, and a notice is shown when a range straddles the boundary.

No query applies a row limit — every builder fetches the full selected window.

## Layout

```
backend/    FastAPI app, pyodbc data layer, metrics services, tests
frontend/   Vite React SPA (filters, load-over-time chart, stage tabs, fraud)
dba/        idle-safe DDL (both tables) + local developer seeder
legacy/     original Streamlit app + reference docs (not deployed)
deployment.yaml   K8s ConfigMap/Secret + backend & frontend Deployments/Services
```

## Local development

### 1. Database (Azure SQL Edge)

Easiest (idempotent — reuses the container if it already exists, so no
"name already in use" / "port already allocated" errors):

```bash
scripts/start-db.sh
```

Or manually — start the existing container if present, otherwise create it:

```bash
docker start aikyc-mssql 2>/dev/null || \
docker run -d --name aikyc-mssql \
  -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='LocalDev123!' \
  -p 1433:1433 -v aikyc-mssql-data:/var/opt/mssql \
  --restart unless-stopped mcr.microsoft.com/azure-sql-edge
```

The named volume keeps `docai` across container recreates. On Apple Silicon let
Docker Desktop handle emulation (do **not** force `--platform`, which triggers a
fresh amd64 pull).

### 2. Create schema + seed data

```bash
cd dba
# apply the schema (idempotent, creates BOTH tables) via sqlcmd (or any client)
sqlcmd -S localhost,1433 -U sa -P 'LocalDev123!' -i live_photo_logs_schema.sql
python local_dev_seed.py   # 7 days -> LIVE_PHOTO_LOGS, days 7..30 -> ARCHIVE
```

The seeder writes to `MSSQL_DATABASE` (default `docai`). Override with env
variables, e.g. `SEED_LIVE_DAYS`, `SEED_ARCHIVE_DAYS`, `SEED_ROWS_PER_DAY`.

Seed data mirrors UAT: the `LIVEPHOTO_UCJv5` source, `<uuid>_<hex8>~<attempt>`
transaction ids, `NOT_FOUND` tracking ids, and the real status vocabulary
(`PASSED` / `FAILED` / `FB01-03` / `NOT REQUIRED`, with `VERIFYTOKEN_STATUS` and
`CALLBACK_STATUS` left NULL when a stage was skipped).

### 3. Backend

```bash
cd backend
cp .env.example .env
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Serves `GET /api/health`, `/api/sources`, `/api/range`, `/api/dashboard`,
`/api/raw`, `/api/raw.csv`,
`/api/fraud/{summary,eventual,never-succeeded}`. All support a
`table=live|archive` selector; `/api/dashboard` also takes `granularity`
(`auto|15m|30m|1h|6h|1d`) and `start_time`/`end_time` (HH:MM, applied per day).
The fraud endpoints take `source`, `start` and `end` so the analysis is scoped
to the dashboard's selected window. `/api/range` returns the available data
window and row count for a table; the UI uses it to snap the date picker when
switching datasets.

#### Credentials: DEV vs GCP Secret Manager

`ENVIRONMENT=DEV` (default) uses the plain `MSSQL_USERNAME` / `MSSQL_PASSWORD`
env values — that is the local Docker setup. Any other value (`UAT`, `PROD`)
makes the backend fetch **username and password from GCP Secret Manager** at
startup via the GKE metadata server (no key file):

| Env var | Purpose |
| --- | --- |
| `ENVIRONMENT` | `DEV` = local env creds; anything else = Secret Manager |
| `GCP_PROJECT_ID` | project holding the secrets |
| `GCP_LOCATION` | e.g. `asia-south1` |
| `MSSQL_USERNAME_SECRET_ID` | default `sm-aikyc-uat-db-username` |
| `MSSQL_PASSWORD_SECRET_ID` | default `sm-aikyc-uat-db-password` |

The pod's service account needs `roles/secretmanager.secretAccessor` on both
secrets (see the Workload Identity note in `deployment.yaml`). A failed fetch
fails the pod at startup rather than serving with stale credentials.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api -> :8000
```

## Dashboard sections

- **KPIs** – total transactions.
- **Load over time** – volume per interval (bars) with bucket-over-bucket
  variation % (secondary axis); granularity + time-of-day window are selectable.
- **Status by stage** – per-date breakdown of the raw DB status values for each
  stage (arbitrary codes such as `FB01`/`FB02` are shown with distinct colours),
  plus **Fraud Attempt** (`FRAUD`/`GENUINE`/`NULL`) and **User Review**
  (`ACCEPT`/`REJECTED`/`REVIEW PENDING`/`NULL`).
- **Latency** – per-stage min/median/max/mean table and box plot (computed
  server-side; no raw points shipped).
- **Exceptions** (collapsible), **Raw data** (collapsible, + CSV download) and
  **Fraud analysis**.

## Load alerts (SMTP)

A standalone worker evaluates per-stage request counts over a sliding window and
emails when a rule is breached. It runs independently of the API/UI (so alerts
fire even when nobody is watching) and is deployed as a single replica.

Rules live in `backend/alerts.example.yaml` (mounted at `/app/alerts.yaml` in
k8s). The file is re-read every cycle; a malformed reload keeps the last good
config. Metrics: `total`, `blink_requests`, `head_nod_requests`,
`authenticity_requests`, `image_seg_requests`, `verify_token_requests`,
`callback_requests`. `source: "*"` aggregates all sources; omit it to evaluate
each source separately. A breach must persist for `breaches_required` cycles,
repeats are suppressed for `cooldown_minutes`, and a recovery email is sent when
the value drops back.

SMTP uses the same environment contract as the standalone AIKYC app:

| Env var | Purpose |
| --- | --- |
| `SMTP_SERVER` / `SMTP_PORT` | relay (UAT: `25`; local Mailpit: `1025`) |
| `EMAIL_SENDER` | From address |
| `EMAIL_RECIVER` | recipients, comma/semicolon separated (`EMAIL_RECEIVER` also accepted) |
| `SMTP_STARTTLS` / `SMTP_SSL` | optional; default off (AIKYC uses plain SMTP) |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | optional auth |

Worker knobs: `ALERT_CONFIG`, `ALERT_TIMEZONE` (default `Asia/Kolkata`, matching
the catalog timestamps), `ALERT_STATE_FILE`, `ALERT_HEARTBEAT_FILE`,
`DASHBOARD_URL`.

Local check with Mailpit:

```bash
docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit
cd backend
ALERT_CONFIG=alerts.example.yaml SMTP_SERVER=localhost SMTP_PORT=1025 \
  EMAIL_SENDER=noreply@localhost EMAIL_RECIVER=noreply@localhost \
  python -m app.alerts.worker --test-email
python -m app.alerts.worker --once --dry-run   # evaluate + log, no mail
open http://localhost:8025
```

Long-running worker: `python -m app.alerts.worker`. In k8s it is the
`ui-dashboard-alerts` Deployment (1 replica); the heartbeat file drives its
liveness probe. The local seed has ~1 event per 5 minutes, so use `threshold: 0`
or a longer window when testing locally.

## Tests

```bash
# backend: fast unit tests (no DB)
cd backend && pytest tests/unit

# backend: live-DB integration tests (requires the Edge container seeded)
LIVE_PHOTO_TEST_LIVE_DB=1 pytest tests/integration

# frontend: component + client tests
cd frontend && npm test
```

## Docker

```bash
docker build -t ui-dashboard-backend:dev  backend/
docker build -t ui-dashboard-frontend:dev frontend/
```

The frontend image serves the build with nginx and proxies `/api/` to the
`ui-dashboard-backend` Service. Deploy with `kubectl apply -f deployment.yaml`
(fill in the image references, namespace and the `MSSQL_PASSWORD` secret first).

The backend image also runs the alert worker (`command:
["python", "-m", "app.alerts.worker"]`); `alerts.yaml` is copied into the image
as a fallback and overridden by the `ui-dashboard-alerts-rules` ConfigMap mount.
