#!/usr/bin/env bash
# One-click stop. Data is kept; the next start continues where it left off.
set -uo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT" || exit 1

if ! docker info >/dev/null 2>&1; then
  if [[ "${CHURNPULSE_IN_GROUP:-}" != 1 ]] && id -nG "$USER" | grep -qw docker; then
    export CHURNPULSE_IN_GROUP=1
    exec newgrp docker <<< "CHURNPULSE_IN_GROUP=1 bash '$PROJECT/scripts/stop.sh'"
  fi
  echo "Cannot talk to Docker."; sleep 5; exit 1
fi

printf "\n  \033[1;36mStopping ChurnPulse...\033[0m\n\n"
docker compose down >/tmp/churnpulse-stop.log 2>&1
printf "  \033[1;32m✔ Stopped. Memory freed. Your data is kept.\033[0m\n"
notify-send -a ChurnPulse -i process-stop "ChurnPulse stopped" "Memory freed. Data is kept." 2>/dev/null
sleep 3
