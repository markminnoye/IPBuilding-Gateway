FROM python:3.11-slim

# Multi-arch support for HA Green (aarch64) and generic OVA (amd64)
WORKDIR /app

# Install only what the gateway needs at runtime
COPY requirements-gateway.txt .
RUN pip install --no-cache-dir -r requirements-gateway.txt

# Copy gateway package (setup.py not needed — module run)
COPY gateway/ ./gateway/

# Supervisor options JSON → env vars script
COPY run.sh .

# Persistent data directory (mapped via addon_config)
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1

# Entry point: run.sh translates options.json → env vars then starts the gateway
CMD ["./run.sh"]