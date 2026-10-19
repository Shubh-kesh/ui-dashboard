# ui-dashboard backend image (FastAPI + pyodbc against MSSQL).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Microsoft ODBC Driver 18 + unixODBC (required by pyodbc).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg2 ca-certificates apt-transport-https unixodbc unixodbc-dev \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY pytest.ini ./

# Non-root runtime user (matches typical runAsUser/runAsGroup: 1000).
RUN groupadd -g 1000 appuser || true \
    && useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin appuser || true \
    && chown -R 1000:1000 /app
USER 1000:1000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
