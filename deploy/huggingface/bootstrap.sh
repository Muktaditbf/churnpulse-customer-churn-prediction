#!/bin/bash
# One-shot: database schema, Kafka topics, then the Flink scoring job.
set -euo pipefail
until /usr/lib/postgresql/16/bin/pg_isready -h 127.0.0.1 -U churnpulse -q; do sleep 1; done
if ! /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U churnpulse -lqt | cut -d'|' -f1 | grep -qw churnpulse; then
  /usr/lib/postgresql/16/bin/createdb -h 127.0.0.1 -U churnpulse churnpulse
  /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U churnpulse -d churnpulse -q -f /opt/churnpulse/infra/postgres/init.sql
  echo "database ready"
fi

K=/opt/kafka/bin
until $K/kafka-broker-api-versions.sh --bootstrap-server 127.0.0.1:9092 >/dev/null 2>&1; do sleep 2; done
create() { $K/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --create --if-not-exists \
             --replication-factor 1 --topic "$1" --partitions "$2" ${3:+--config $3}; }
create customer-events 6 retention.ms=-1
create churn-predictions 6
create churn-stats 1
echo "topics ready"

exec bash /opt/churnpulse/streaming/flink_job/submit.sh
