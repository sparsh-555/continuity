#!/usr/bin/env bash
#
# Start Continuity's demo world from cold, in one command.
#
#   ./demo.sh              rebuild the world, check, run
#   ./demo.sh --keep       keep the world the last run left behind
#   ./demo.sh --check      the checks only, change nothing
#   ./demo.sh --stop       stop whatever this script started
#   ./demo.sh --live       go to the distributor instead of replaying recordings
#
# Everything OPERATING.md §1 and §2 ask you to type, in the order it asks, with
# the reasons kept next to the failures. It is not a replacement for that document,
# it is the part before RUNNER.md's run-through that never varies.
#
# **The world is rebuilt every time.** A world left over from an earlier run still
# holds that run's change notice and the decisions it raised, so the walk-through
# opens with the mail already read and step 4 has nothing left to announce. The
# rebuild takes about three seconds and ends with the mailbox read position moved
# past everything already in the inbox. `--keep` is for going back to a run-through
# that is still in progress.
#
# **The database is always named on the command line.** `backend/.env` points
# DATABASE_URL at production Neon, so a local run that forgets to say otherwise
# writes real rows. Every command below carries its own.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
ROOT="$PWD"
RUN_DIR="$ROOT/.demo"
DB="postgresql:///continuity_demo"
TEST_DB="postgresql:///continuity_test"
API_PORT=8000
UI_PORT=5173
PY="$ROOT/.venv/bin/python"

MODE=run
RESET=1
# **Replay by default.** Every distributor call the demo makes is recorded in
# `backend/fixtures/`, 617 of them committed, and replaying takes a review from
# over two minutes against a live JLCPCB to under a second — same frames, same
# verdicts, same margins, because only the distributor's answers come off disk
# and the engine, the rules, KiCad and the model all still run. `--live` goes to
# the network, which is how new recordings are made.
FIXTURES=1
WITH_MAIL=1

while [ $# -gt 0 ]; do
  case "$1" in
    --check)    MODE=check ;;
    --stop)     MODE=stop ;;
    --reset)    RESET=1 ;;
    --keep)     RESET=0 ;;
    --live)     FIXTURES=0 ;;
    --fixtures) FIXTURES=1 ;;
    --no-mail)  WITH_MAIL=0 ;;
    -h|--help)  sed -n '3,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -t 1 ]; then
  DIM=$'\033[2m'; RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; OFF=$'\033[0m'
else
  DIM=''; RED=''; YEL=''; GRN=''; OFF=''
fi

ok()   { printf '  %s✓%s %s\n' "$GRN" "$OFF" "$1"; }
warn() { printf '  %s!%s %s\n' "$YEL" "$OFF" "$1"; }
die()  { printf '  %s✗%s %s\n' "$RED" "$OFF" "$1"; exit 1; }
note() { printf '    %s%s%s\n' "$DIM" "$1" "$OFF"; }

mkdir -p "$RUN_DIR"

# ── stopping ─────────────────────────────────────────────────────────────────

stop_one() {
  # Two statements, not one: `local a=$1 b=$a` reads `a` before it is assigned, which
  # under `set -u` is a fatal error inside the very function that cleans up.
  local name="$1"
  local pidfile="$RUN_DIR/$name.pid"
  if [ -f "$pidfile" ]; then
    local pid; pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      # Vite and uvicorn both spawn children; the process group goes with them.
      kill -- "-$pid" 2>/dev/null || true
      ok "stopped $name (pid $pid)"
    fi
    rm -f "$pidfile"
  fi
}

stop_all() { stop_one api; stop_one ui; }

if [ "$MODE" = stop ]; then
  echo "Stopping"
  stop_all
  exit 0
fi

# ── checks ───────────────────────────────────────────────────────────────────

echo "Checking"

[ -x "$PY" ] || die "no .venv at $PY — Anaconda's Python cannot import langgraph"
ok "python $("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"

pg_isready -q || die "postgres is not accepting connections"
ok "postgres"

if psql -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw continuity_demo; then
  ok "database continuity_demo"
else
  createdb continuity_demo && ok "database continuity_demo (created)"
fi

if psql -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw continuity_test; then
  ok "database continuity_test"
else
  warn "no continuity_test — only needed to run the suite"
  note "createdb continuity_test"
fi

if [ -d "$ROOT/frontend/node_modules" ]; then
  ok "frontend dependencies"
else
  warn "installing frontend dependencies"
  (cd "$ROOT/frontend" && bun install >/dev/null)
  ok "frontend dependencies"
fi

# The model key. Never printed, only asked about: scrollback outlives the command.
if (cd "$ROOT/backend" && "$PY" -c 'from continuity import llm; raise SystemExit(0 if llm.available() else 1)'); then
  ok "model key"
else
  warn "no model key — reading a change notice is the one step that needs it"
  note "CONTINUITY_LLM_API_KEY in backend/.env; everything else still runs"
fi

if (cd "$ROOT/backend" && "$PY" -c 'from continuity import env, mail; env.load(); raise SystemExit(0 if mail.configured() else 1)'); then
  ok "mailbox configured"
else
  WITH_MAIL=0
  warn "no mailbox — the notice arrives by UPLOAD ONE INSTEAD rather than by email"
  note "the three CONTINUITY_MAIL_* variables in backend/.env"
fi

recorded=$(ls "$ROOT"/backend/fixtures/*.json 2>/dev/null | wc -l | tr -d ' ')
if [ "$FIXTURES" = 1 ]; then
  if [ "${recorded:-0}" -gt 0 ]; then
    ok "$recorded recorded distributor calls — replaying, not calling out"
  else
    warn "no recordings in backend/fixtures — every distributor call will fail"
    note "./demo.sh --live records them as it goes"
  fi
else
  warn "--live: every distributor call goes to the network and is recorded as it goes"
  note "a review took over 140 s live on 10 Sep and under 1 s replayed"
fi

if docker info >/dev/null 2>&1; then
  if docker image inspect kicad/kicad:9.0 >/dev/null 2>&1; then
    ok "kicad image"
  else
    warn "kicad/kicad:9.0 is not pulled — the BOARD view will be unavailable"
    note "docker pull --platform linux/amd64 kicad/kicad:9.0   # about 2 GB, once"
  fi
else
  warn "docker is not running — the BOARD view will be unavailable"
fi

if [ "$MODE" = check ]; then
  echo
  echo "Checks only. Nothing was started."
  exit 0
fi

# ── the world ────────────────────────────────────────────────────────────────

# Both ports, before anything is written rather than after. Rebuilding the world is
# the first thing this script does that cannot be undone, and finding out afterwards
# that a run is already up would mean losing a world to a message about a port.
for port in "$API_PORT" "$UI_PORT"; do
  if lsof -ti tcp:"$port" >/dev/null 2>&1; then
    die "port $port is in use — ./demo.sh --stop, or close whatever holds it"
  fi
done

echo
echo "The world"

seeded=$(psql "$DB" -tAc "select count(*) from product_lines" 2>/dev/null || echo 0)
if [ "$RESET" = 1 ] || [ "${seeded:-0}" -eq 0 ]; then
  # `--reset` on an empty database is refused, so only pass it when there is
  # something to replace.
  args=("$DB")
  [ "${seeded:-0}" -gt 0 ] && args+=(--reset)
  (cd "$ROOT/backend" && PYTHONPATH=. "$PY" tools/seed_world.py "${args[@]}") | sed 's/^/  /'
else
  ok "$seeded product lines kept — whatever the last run left, notices and decisions included"
  note "./demo.sh with no arguments rebuilds it"
fi

# ── running ──────────────────────────────────────────────────────────────────

echo
echo "Running"

api_env=(
  "DATABASE_URL=$DB"
  "CONTINUITY_KICAD=docker"
)
[ "$WITH_MAIL" = 1 ] && api_env+=("CONTINUITY_MAIL_ORG=engineer@northwind.example")
[ "$FIXTURES" = 1 ] && api_env+=("CONTINUITY_FIXTURES=1")

(
  cd "$ROOT/backend"
  # Its own process group, so --stop takes the children with it.
  set -m
  env "${api_env[@]}" "$PY" -m uvicorn continuity.api.app:app --port "$API_PORT" \
    > "$RUN_DIR/api.log" 2>&1 &
  echo $! > "$RUN_DIR/api.pid"
)

(
  cd "$ROOT/frontend"
  set -m
  env "VITE_API_URL=http://localhost:$API_PORT" \
    bun run dev --strictPort --port "$UI_PORT" > "$RUN_DIR/ui.log" 2>&1 &
  echo $! > "$RUN_DIR/ui.pid"
)

trap 'echo; echo "Stopping"; stop_all; exit 0' INT TERM

wait_for() {
  local what="$1" url="$2" log="$3" tries=60
  while [ $tries -gt 0 ]; do
    # Any answer at all means it is listening. `/lines` replies 401 before sign-in,
    # which is a perfectly good sign of life.
    if curl -s -o /dev/null --max-time 2 "$url"; then ok "$what"; return 0; fi
    if ! kill -0 "$(cat "$RUN_DIR/${what}.pid")" 2>/dev/null; then
      printf '  %s✗%s %s died on startup:\n' "$RED" "$OFF" "$what"
      tail -15 "$log" | sed 's/^/    /'
      stop_all
      exit 1
    fi
    sleep 1
    tries=$((tries - 1))
  done
  die "$what did not come up — see $log"
}

wait_for api "http://localhost:$API_PORT/lines" "$RUN_DIR/api.log"
wait_for ui  "http://localhost:$UI_PORT/"       "$RUN_DIR/ui.log"

# That the API is on the seeded database, asked rather than inferred. The runner used to
# say to look for `persistence: postgres` in the startup lines; nothing configures logging, so
# `log.info` never reaches the console and that line has never appeared. Signing in is the
# thing the log line was standing in for anyway: no accounts, no postgres.
if curl -s -o /dev/null --max-time 5 -X POST "http://localhost:$API_PORT/auth/login" \
     -H 'Content-Type: application/json' \
     -d '{"email":"engineer@northwind.example","password":"continuity-demo-2026"}' \
     -w '%{http_code}' | grep -q 200; then
  ok "signed in as the engineer"
else
  warn "the seeded accounts do not work — the API may not be on continuity_demo"
fi

echo
printf '  %shttp://localhost:%s%s\n' "$GRN" "$UI_PORT" "$OFF"
echo
echo "  engineer@northwind.example      continuity-demo-2026   engineering"
echo "  procurement@northwind.example   continuity-demo-2026   procurement"
echo "  production@northwind.example    continuity-demo-2026   production"
echo "  quality@northwind.example       continuity-demo-2026   quality"
echo
if [ "$WITH_MAIL" = 1 ]; then
  echo "  Forward docs/world-finals/notices/PCN-2026-114.pdf to the demo mailbox for step 4."
  note "the read position was moved past everything already in the inbox, so only new mail arrives"
else
  echo "  No mailbox: use UPLOAD ONE INSTEAD on /changes with the same PDF."
fi
echo
if [ "$FIXTURES" = 1 ]; then
  note "distributor calls are replayed from backend/fixtures — disclose this, never hide it"
fi
note "walkthrough: docs/world-finals/RUNNER.md   what to say: DEMO-DAY.md"
note "logs: .demo/api.log  .demo/ui.log"
note "ctrl-c stops both"
echo

# Hold the terminal so ctrl-c reaches the trap.
while kill -0 "$(cat "$RUN_DIR/api.pid")" 2>/dev/null; do sleep 1; done
warn "the API exited — see .demo/api.log"
stop_all
