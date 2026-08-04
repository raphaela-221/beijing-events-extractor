#!/usr/bin/env bash
# macOS entry point for Step 2: canonical Events List.xlsx -> calendar website.
# Usage:
#   ./run.sh                                    use ../01_event_list_output/Events List.xlsx
#   ./run.sh /path/to/file.xlsx                 use a specific source Excel
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVENT_LIST_DIR="$SCRIPT_DIR/../01_event_list_output"
CANONICAL_SOURCE="$EVENT_LIST_DIR/Events List.xlsx"
PYTHON_CMD="${PYTHON_CMD:-python3}"

SOURCE="${1:-$CANONICAL_SOURCE}"

if [ ! -f "$SOURCE" ]; then
    echo "错误：找不到源 Excel: $SOURCE"
    echo "请先确认 01_event_list_output/Events List.xlsx 存在，或传入自定义路径。"
    exit 1
fi

echo "源文件: $SOURCE"
echo

echo "[1/4] Extracting High events from source Excel..."
"$PYTHON_CMD" "$SCRIPT_DIR/run_pipeline.py" extract --source "$SOURCE"

echo
echo "[2/4] Generating/enriching monthly themes (incremental)..."
"$PYTHON_CMD" "$SCRIPT_DIR/run_pipeline.py" themes --year 2026 || {
    echo "Theme enrichment skipped or failed. You can re-run it later with:"
    echo "  python3 run_pipeline.py themes --year 2026"
}

echo
echo "[3/4] Verifying calendar pages..."
"$PYTHON_CMD" "$SCRIPT_DIR/run_pipeline.py" calendar

echo
echo "[4/4] Packaging viewer-facing files for sharing..."
"$PYTHON_CMD" "$SCRIPT_DIR/run_pipeline.py" package

echo
echo "Pipeline finished."
echo "  - Open index.html to preview."
echo "  - Upload the 02_web_output/ folder to OneDrive and share the folder link."
