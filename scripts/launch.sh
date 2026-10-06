#!/usr/bin/env bash
# One-click start: brings up the whole platform and opens the dashboard
# as soon as it is ready. Used by the "ChurnPulse" desktop icon.
set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="http://localhost:3000"
cd "$PROJECT" || exit 1

green() { printf "\033[1;32m%s\033[0m\n" "$*"; }
info()  { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }
fail()  {
  printf "\n\033[1;31m✖ %s\033[0m\n" "$*"
  notify-send -a ChurnPulse -i dialog-error "ChurnPulse could not start" "$*" 2>/dev/null
  read -rp "Press Enter to close this window..." < /dev/tty
  exit 1
}

# Docker access: if this login session predates joining the docker group,
# re-run this script inside that group (no password needed).
if ! docker info >/dev/null 2>&1; then
  if [[ "${CHURNPULSE_IN_GROUP:-}" != 1 ]] && id -nG "$USER" | grep -qw docker; then
    export CHURNPULSE_IN_GROUP=1
    exec newgrp docker <<< "CHURNPULSE_IN_GROUP=1 bash '$PROJECT/scripts/launch.sh'"
  fi
  systemctl is-active --quiet docker || fail "Docker is not running. Start it with: sudo systemctl start docker"
  fail "Cannot talk to Docker. Log out and back in once, then try again."
fi

clear
printf "\n  \033[1;36mChurnPulse\033[0m — real-time churn prediction\n\n"

# Already running? Just open the website.
if curl -sf "$URL/api/health" >/dev/null 2>&1; then
  green "✔ ChurnPulse is already running."
  xdg-open "$URL" >/dev/null 2>&1 &
  sleep 3
  exit 0
fi

# First run on a new machine: build the images.
if ! docker image inspect churnpulse/app:1.0 churnpulse/flink:1.0 churnpulse/frontend:1.0 >/dev/null 2>&1; then
  info "Building the app (first time only, ~5 minutes)..."
  docker buildx bake --allow=network.host -f docker-compose.yml --load >/tmp/churnpulse-build.log 2>&1 \
    || fail "Build failed - see /tmp/churnpulse-build.log"
fi

info "Starting 13 services (Kafka, Flink, database, API, website, monitoring)..."
docker compose up -d >/tmp/churnpulse-start.log 2>&1 || fail "Could not start - see /tmp/churnpulse-start.log"

info "Waiting for the API..."
for _ in $(seq 1 90); do
  curl -sf http://localhost:8000/api/health >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://localhost:8000/api/health >/dev/null 2>&1 || fail "The API did not start. Run 'make logs' in $PROJECT."

info "Scoring all customers in the stream..."
total=7043
for _ in $(seq 1 120); do
  scored=$(curl -sf http://localhost:8000/api/stats | python3 -c "import json,sys; print(json.load(sys.stdin)['customers_scored'])" 2>/dev/null || echo 0)
  pct=$(( scored * 100 / total ))
  bar=$(printf "%-40s" "$(printf '#%.0s' $(seq 1 $(( pct * 40 / 100 + 1 ))))")
  printf "\r  [%s] %3d%%  (%d / %d)" "${bar// /.}" "$pct" "$scored" "$total"
  [[ "$scored" -ge "$total" ]] && break
  sleep 2
done
echo

green "✔ ChurnPulse is ready!  Opening $URL"
notify-send -a ChurnPulse -i applications-science "ChurnPulse is running" "Dashboard: $URL" 2>/dev/null
xdg-open "$URL" >/dev/null 2>&1 &

printf "\n  To stop it later, double-click \033[1mStop ChurnPulse\033[0m on your desktop.\n"
printf "  This window closes in 10 seconds.\n"
sleep 10
