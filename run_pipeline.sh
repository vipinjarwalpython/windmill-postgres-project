#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  run_pipeline.sh
#  ────────────────
#  Runs all 4 pipeline steps IN ORDER using Docker.
#  Each step must finish successfully before the next starts.
#
#  Usage:
#    chmod +x run_pipeline.sh
#    ./run_pipeline.sh
# ══════════════════════════════════════════════════════════════

set -e   # stop immediately if any step fails

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'   # no color

log()  { echo -e "${BLUE}[PIPELINE]${NC} $1"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $1"; }
fail() { echo -e "${RED}[ FAIL ]${NC} $1"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     Windmill Pipeline — Docker Run       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Build all images first ─────────────────────────────────────
log "Building Docker images..."
docker compose build --quiet
ok "Images built"

# ── Step 1: Load Data ──────────────────────────────────────────
echo ""
log "▶  STEP 1/4 — Load Data"
docker compose run --rm load_data \
  || fail "STEP 1 failed"
ok "Step 1 complete"

# ── Step 2: Process Data ───────────────────────────────────────
echo ""
log "▶  STEP 2/4 — Process Data"
docker compose run --rm process_data \
  || fail "STEP 2 failed"
ok "Step 2 complete"

# ── Step 3: Store Data ─────────────────────────────────────────
echo ""
log "▶  STEP 3/4 — Store Data"
docker compose run --rm store_data \
  || fail "STEP 3 failed"
ok "Step 3 complete"

# ── Step 4: Notify ─────────────────────────────────────────────
echo ""
log "▶  STEP 4/4 — Notify"
docker compose run --rm notify \
  || fail "STEP 4 failed"
ok "Step 4 complete"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅  Pipeline completed successfully!   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
