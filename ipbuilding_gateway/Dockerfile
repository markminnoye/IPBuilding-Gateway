FROM python:3.11-slim

# Multi-arch support for HA Green (aarch64) and generic OVA (amd64)
WORKDIR /app

# ARP-first discovery runs `ping` during POST /api/v1/discover and init sweeps
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install only what the gateway needs at runtime
COPY requirements-gateway.txt .
RUN pip install --no-cache-dir -r requirements-gateway.txt

# Copy gateway package (setup.py not needed — module run)
COPY gateway/ ./gateway/

# config.yaml is the runtime version source of truth — gateway/version.py
# resolves it relative to the installed gateway/ package. Shipping the
# YAML keeps `__version__` (= /api/v1/status) in sync with what Supervisor
# advertises, even after a release where the image tag matches the YAML.
COPY config.yaml ./ipbuilding_gateway/config.yaml

# Supervisor options JSON → env vars script
COPY run.sh .
RUN chmod +x ./run.sh

# Supervisor /data (options.json) and /config (addon_config:rw for devices.json)
RUN mkdir -p /data /config

ENV PYTHONUNBUFFERED=1

# Entry point: run.sh translates options.json → env vars then starts the gateway
CMD ["./run.sh"]