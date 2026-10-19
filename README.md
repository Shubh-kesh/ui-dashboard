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

```bash
docker run -d --name aikyc-mssql -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='LocalDev123!' \
  -p 1433:1433 mcr.microsoft.com/azure-sql-edge
```

### 2. Create schema + seed data

```bash
cd dba
# apply the schema (idempotent, creates BOTH tables) via sqlcmd (or any client)
sqlcmd -S localhost,1433 -U sa -P 'LocalDev123!' -i live_photo_logs_schema.sql
python local_dev_seed.py   # 7 days -> LIVE_PHOTO_LOGS, days 7..30 -> ARCHIVE
```

The seeder writes to `MSSQL_DATABASE` (default `docai`). Override with env
variables, e.g. `SEED_LIVE_DAYS`, `SEED_ARCHIVE_DAYS`, `SEED_ROWS_PER_DAY`.

### 3. Backend

```bash
cd backend
cp .env.example .env
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Serves `GET /api/health`, `/api/sources`, `/api/dashboard`, `/api/raw`,
`/api/raw.csv`, `/api/fraud/{summary,total-users,eventual,burst}`. All support a
`table=live|archive` selector; `/api/dashboard` also takes `granularity`
(`auto|15m|30m|1h|6h|1d`) and `start_time`/`end_time` (HH:MM, applied per day).

### 4. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api -> :8000
```

## Dashboard sections

- **KPIs** – total transactions, callback success rate, average callback latency.
- **Load over time** – volume per interval (bars) with bucket-over-bucket
  variation % (secondary axis); granularity + time-of-day window are selectable.
- **Status by stage** – per-date status breakdown for each stage, plus
  **Fraud Attempt** (`FRAUD`/`GENUINE`/`NULL`) and **User Review**
  (`ACCEPT`/`REJECTED`/`REVIEW PENDING`/`NULL`).
- **Latency** – per-stage min/Q1/median/Q3/max/mean/P95 table and box plot
  (computed server-side; no raw points shipped).
- **Exceptions**, **Raw data** (+ CSV download) and **Fraud analysis**.

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
