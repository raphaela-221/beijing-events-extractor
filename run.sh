#!/usr/bin/env bash
# Top-level launcher for the Beijing events pipeline.
# Usage:
#   ./run.sh              # interactive menu
#   ./run.sh step1        # run Step 1 with default --concert
#   ./run.sh step1 --only-input
#   ./run.sh step2        # run Step 2

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_CMD="${PYTHON_CMD:-python3}"

run_step1() {
    echo
    echo "[Step 1] 从 01_raw_input/ 提取并增量合并事件清单..."
    "$PYTHON_CMD" "$SCRIPT_DIR/01_event_extractor/main.py" --concert "$@"
    echo
    echo "Step 1 完成。输出在 01_event_list_output/。"
    echo "接下来可运行 ./run.sh step2 生成日历看板。"
}

run_step2() {
    echo
    echo "[Step 2] 生成日历看板..."
    "$SCRIPT_DIR/02_calendar/run.sh"
    echo
    echo "Step 2 完成。分享包在 02_web_output/。"
}

# Command-line mode
if [ "$1" == "step1" ]; then
    shift
    run_step1 "$@"
    exit 0
fi

if [ "$1" == "step2" ]; then
    run_step2
    exit 0
fi

# Interactive menu
while true; do
    echo
    echo "=============================="
    echo "   北京大事件信息提取"
    echo "=============================="
    echo "[1] 构建事件清单（Step 1）"
    echo "[2] 生成日历看板（Step 2）"
    echo "[0] 退出"
    echo
    read -rp "请选择 [1/2/0]: " choice
    case "$choice" in
        1) run_step1 ;;
        2) run_step2 ;;
        0) exit 0 ;;
        *) echo "无效选择，请重新输入。" ;;
    esac
done
