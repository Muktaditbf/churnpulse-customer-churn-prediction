# One image for the API and the event simulator (same code, different command).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    CHURNPULSE_ROOT=/app CHURNPULSE_MODELS=/app/models

WORKDIR /app
# LightGBM needs the OpenMP runtime, which the slim image leaves out.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements /app/requirements
RUN pip install -r requirements/serving.txt

COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-deps /app

COPY api /app/api
COPY streaming/simulator /app/streaming/simulator
COPY data/processed /app/data/processed

RUN useradd --create-home --uid 1000 app && mkdir -p /app/models && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"
CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
