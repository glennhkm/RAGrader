#!/usr/bin/env bash
# Week 1-3 materials -> Week 4 quiz demo against a running API.
#
#   RAG_API_URL=http://127.0.0.1:8000 ./examples/week1_to_week4_quiz/run_demo.sh
#
# Optional: RAG_API_TOKEN (Bearer token), NAMESPACE (default net-101-demo), PYTHON.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$HERE/../../backend" && pwd)"
PYTHON="${PYTHON:-python3}"
NAMESPACE="${NAMESPACE:-net-101-demo}"
OUT="${OUT:-$HERE/graded.csv}"

cli() { (cd "$BACKEND" && "$PYTHON" -m src.cli "$@"); }

echo "==> Ingesting materials into namespace '$NAMESPACE'"
for week in 1 2 3 4; do
  # Week 4 is ingested on purpose: the quiz filter below must exclude it.
  cli ingest --namespace "$NAMESPACE" --module "week-$week" "$HERE/materials/week-$week.txt"
done

echo "==> Grading the Week 4 quiz, scoped to week-1..week-3"
cli grade-csv --namespace "$NAMESPACE" \
  --input "$HERE/answers.csv" --output "$OUT" \
  --rubric "$HERE/rubric.json" --max-grade 100 \
  --module week-1 --module week-2 --module week-3 \
  --review-threshold 0.6

echo "==> Results written to $OUT"
