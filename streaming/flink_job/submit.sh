#!/bin/bash
# Submit the scoring job once Flink is ready - and never twice.
set -euo pipefail
JM=http://flink-jobmanager:8081
JOB_NAME=churnpulse-realtime-scoring

until curl -sf "$JM/overview" >/dev/null; do echo "waiting for the JobManager..."; sleep 3; done
until [ "$(curl -sf "$JM/overview" | python -c 'import json,sys; print(json.load(sys.stdin)["slots-total"])')" -gt 0 ]; do
  echo "waiting for a TaskManager slot..."; sleep 3
done

if curl -sf "$JM/jobs/overview" | python -c "
import json, sys
jobs = json.load(sys.stdin)['jobs']
alive = {'RUNNING', 'CREATED', 'INITIALIZING', 'RESTARTING'}
sys.exit(0 if any(j['name'] == '$JOB_NAME' and j['state'] in alive for j in jobs) else 1)"; then
  echo "$JOB_NAME is already running - nothing to do."
  exit 0
fi

echo "submitting $JOB_NAME"
exec flink run --detached \
  -Drest.address=flink-jobmanager -Drest.port=8081 \
  -pyclientexec /opt/venv/bin/python -pyexec /opt/venv/bin/python \
  -py /opt/flink/usrlib/job.py
