#!/bin/bash
# Prepare fresh state (the demo resets on every restart), then hand over to supervisord.
set -euo pipefail
mkdir -p /data/pg /data/kafka /data/flink-checkpoints /tmp/nginx

if [ ! -s /data/pg/PG_VERSION ]; then
  /usr/lib/postgresql/16/bin/initdb -D /data/pg -U churnpulse --auth=trust >/dev/null
fi
if [ ! -f /data/kafka/meta.properties ]; then
  /opt/kafka/bin/kafka-storage.sh format --standalone -t "$(/opt/kafka/bin/kafka-storage.sh random-uuid)" \
    -c /opt/churnpulse/deploy/kafka.properties >/dev/null
fi
exec supervisord -c /opt/churnpulse/deploy/supervisord.conf
