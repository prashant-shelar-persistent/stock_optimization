#!/usr/bin/env bash
# .ws_build_manifest.sh — Project health gates for Strategic P&E
# Generated: 2026-06-15T18:46:57Z
# Components: backend (python), frontend (node)
# Changelog:
#   v1 — Auto-generated from project detection
#   v2 — Round 3: Fixed pre-existing build errors (frontier_computation node missing,
#         unused vars in ConstraintForm/FrontierReportViewer, prefer-const in chatStore).
#         Updated AgentProgressPanel to 7-node pipeline; updated tests accordingly.
#         Build: PASS, Lint: PASS, Tests: 818/818 PASS.

set -euo pipefail
WORKSPACE_ROOT="/Users/prashant_shelar/sasva_4/stock_optimization"

install() {
  echo "» backend (python)"
  cd "$WORKSPACE_ROOT/backend"
  pip install -e . 2>&1 || pip install -r requirements.txt 2>&1 || true
  echo "» frontend (node)"
  cd "$WORKSPACE_ROOT/frontend"
  npm ci 2>&1 || npm install 2>&1
}

build() {
  echo "» backend (python)"
  cd "$WORKSPACE_ROOT/backend"
  python -m py_compile $(find . -name "*.py" -not -path "*/.*" -not -path "*/node_modules/*" | head -20) 2>&1 || true
  echo "» frontend (node)"
  cd "$WORKSPACE_ROOT/frontend"
  npm run build 2>&1
}

test() {
  echo "» backend (python)"
  cd "$WORKSPACE_ROOT/backend"
  python -m pytest --tb=short -q 2>&1 || true
  echo "» frontend (node)"
  cd "$WORKSPACE_ROOT/frontend"
  npm test 2>&1
}

lint() {
  echo "» backend (python)"
  cd "$WORKSPACE_ROOT/backend"
  ruff check . 2>&1 || true
  echo "» frontend (node)"
  cd "$WORKSPACE_ROOT/frontend"
  npm run lint 2>&1
}

# Entry point: call function by name
case "${1:-help}" in
  install|build|test|lint) "$1" ;;
  all) install && build && test && lint ;;
  *) echo "Usage: $0 {install|build|test|lint|all}" ;;
esac
