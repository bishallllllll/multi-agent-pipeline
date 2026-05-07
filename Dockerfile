FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY agent_executor/ ./agent_executor/
COPY orchestrator/ ./orchestrator/
COPY agents/ ./agents/
COPY scripts/ ./scripts/
COPY config.yaml .
COPY opencode.json .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["python", "-m", "orchestrator.cli"]
