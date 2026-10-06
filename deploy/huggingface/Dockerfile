# ChurnPulse public demo: the full real-time stack (Kafka, Flink, PostgreSQL,
# FastAPI, simulator, React) in one container for Hugging Face Spaces.
# Build context is the repository root:  docker build -f deploy/huggingface/Dockerfile .

FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN VITE_PUBLIC_DEMO=1 npm run build

FROM flink:2.2.1-java17

ARG KAFKA_CONNECTOR=5.0.0-2.2

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-dev build-essential curl \
      postgresql-16 nginx libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Kafka (KRaft, single node) and Flink's Kafka connector.
COPY --from=apache/kafka:3.9.1 /opt/kafka /opt/kafka
RUN curl -fsSL -o /opt/flink/lib/flink-sql-connector-kafka-${KAFKA_CONNECTOR}.jar \
      https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/${KAFKA_CONNECTOR}/flink-sql-connector-kafka-${KAFKA_CONNECTOR}.jar

# One Python environment for Flink, the API and the simulator (pinned versions the models need).
COPY requirements /opt/churnpulse/requirements
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir apache-flink==2.2.1 supervisor==4.3.0 \
      -r /opt/churnpulse/requirements/serving.txt
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /opt/churnpulse
COPY pyproject.toml README.md ./
COPY src src
RUN pip install --no-cache-dir --no-deps .
COPY api api
COPY streaming streaming
COPY models models
COPY data/processed data/processed
COPY infra/postgres/init.sql infra/postgres/init.sql
COPY --from=frontend /app/dist /opt/churnpulse/web
COPY deploy/huggingface/ ./deploy/
# Flink's own entrypoint merges these settings into conf/config.yaml.
RUN FLINK_PROPERTIES="$(grep -v '^#' deploy/flink-conf.yaml)" /docker-entrypoint.sh true \
 && mkdir -p /data && chown -R 1000:1000 /data /opt/churnpulse /opt/flink /opt/kafka/ \
 && chmod +x deploy/*.sh

ENV CHURNPULSE_ROOT=/opt/churnpulse CHURNPULSE_MODELS=/opt/churnpulse/models \
    DATABASE_URL=postgresql://churnpulse@127.0.0.1:5432/churnpulse \
    KAFKA_BOOTSTRAP=127.0.0.1:9092 FLINK_JOBMANAGER=127.0.0.1 JOB_PY=/opt/churnpulse/streaming/flink_job/job.py \
    JOB_PARALLELISM=2 EVENTS_PER_SEC=3 PYTHONUNBUFFERED=1

# Hugging Face runs containers as uid 1000.
USER 1000
EXPOSE 7860
ENTRYPOINT []
CMD ["/opt/churnpulse/deploy/start.sh"]
