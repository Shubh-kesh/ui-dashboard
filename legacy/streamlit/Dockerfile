# Replace with your pre-built base image name (the one with required packages baked in)
ARG BASE_IMAGE=your-base-image-name:tag
FROM ${BASE_IMAGE}

WORKDIR /app

# Create uid/gid 1000 to match deployment.yaml's securityContext (runAsUser/runAsGroup: 1000).
# `|| true` guards against the base image already having a user/group at 1000.
RUN groupadd -g 1000 appuser || true && \
    useradd -u 1000 -g 1000 -m -s /usr/sbin/nologin appuser || true

# If your base image already has requirements.txt packages installed, this is a no-op safety net.
# Keeping it ensures the image is reproducible even if the base image changes later.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py metrics.py charts.py uidb_client.py ./

# Streamlit writes config/cache to $HOME/.streamlit at runtime -- give uid 1000 a writable
# home and make sure it (and /app) are actually owned by 1000:1000, not just chmod'd.
ENV HOME=/home/appuser
RUN mkdir -p /home/appuser/.streamlit && \
    chown -R 1000:1000 /app /home/appuser

# Streamlit config: run headless, listen on all interfaces, disable telemetry
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

# Matches the readinessProbe/livenessProbe path in deployment.yaml
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8501/_stcore/health || exit 1

USER 1000:1000

ENTRYPOINT []
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

