# ui-dashboard

LivePhoto **KYC dashboard**: transaction volume, pipeline funnel, per-stage status,
latency and fraud analysis over the `LIVE_PHOTO_LOGS` telemetry table.

It replaces the original Streamlit monolith (kept under `legacy/streamlit/`) with:

| Layer    | Stack                                                             |
| -------- | ----------------------------------------------------------------- |
| Backend  | FastAPI + pandas + pyodbc (direct MSSQL, no uidb proxy)           |
| Frontend | Vite + React + TypeScript + Tailwind + TanStack Query + Plotly    |
| Local DB | Azure SQL Edge container (`aikyc-mssql`) with the full schema      |

## Layout

```
backend/    FastAPI app, pyodbc data layer, metrics services, tests
frontend/   Vite React SPA (charts, filters, raw table, fraud section)
dba/        idle-safe DDL + local developer seeder
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
# apply the schema (idempotent) via sqlcmd (or any MSSQL client)
sqlcmd -S localhost,1433 -U sa -P 'LocalDev123!' -d docai -i live_photo_logs_schema.sql
python local_dev_seed.py            # multi-day / multi-source / multi-attempt data
```

The seeder writes to `MSSQL_DATABASE` (default `docai`). Override with env
variables, e.g. `MSSQL_DATABASE=docai` `LIVE_PHOTO_TABLE=LIVE_PHOTO_LOGS`.

### 3. Backend

```bash
cd backend
cp .env.example .env
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Serves `GET /api/health`, `/api/sources`, `/api/dashboard`, `/api/raw`,
`/api/raw.csv`, `/api/fraud/{summary,total-users,eventual,burst}`.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api -> :8000
```

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
