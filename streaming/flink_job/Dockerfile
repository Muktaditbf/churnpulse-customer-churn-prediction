# Flink with Python support, the Kafka connector and the ChurnPulse model code.
FROM flink:2.2.1-java17

ARG KAFKA_CONNECTOR=5.0.0-2.2

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv python3-dev build-essential curl \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/bin/python3 /usr/bin/python

# Kafka connector for the DataStream API, plus the Prometheus metrics reporter.
RUN curl -fsSL -o /opt/flink/lib/flink-sql-connector-kafka-${KAFKA_CONNECTOR}.jar \
      https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/${KAFKA_CONNECTOR}/flink-sql-connector-kafka-${KAFKA_CONNECTOR}.jar \
 && mkdir -p /opt/flink/plugins/metrics-prometheus \
 && (cp /opt/flink/opt/flink-metrics-prometheus-*.jar /opt/flink/plugins/metrics-prometheus/ 2>/dev/null || true)

# Same pinned versions the model was trained with - a pickled model needs them.
COPY requirements/runtime.txt /tmp/runtime.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir apache-flink==2.2.1 -r /tmp/runtime.txt
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml README.md /opt/churnpulse/
COPY src /opt/churnpulse/src
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps /opt/churnpulse

COPY streaming/flink_job/job.py streaming/flink_job/submit.sh /opt/flink/usrlib/
ENV CHURNPULSE_MODELS=/opt/churnpulse/models
RUN mkdir -p /opt/churnpulse/models /opt/flink/checkpoints && chown -R flink:flink /opt/flink /opt/churnpulse
USER flink
