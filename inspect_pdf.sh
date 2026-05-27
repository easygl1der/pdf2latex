#!/bin/bash
# ==============================================================================
# PDF 视觉深度分析工具 (inspect_pdf.sh)
#
# 同时分析 PDF 首页（模板/元数据）和末页（文献引用格式），两路 LLM 调用并行执行。
#
# 输出:
#   - 前三页: LaTeX 模板类型、\maketitle 所需字段（标题/作者/日期/机构等）
#   - 后三页: 引用格式识别（IEEE/APA/...）、bibtex 包建议、引用样例
#
# 💡 使用方式:
#   ./inspect_pdf.sh pdf/test-6.pdf
#   ./inspect_pdf.sh pdf/test-6.pdf gemma4:31b-cloud
#   ./inspect_pdf.sh pdf/test-6.pdf gemini-3-flash-preview:cloud -np
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_MODEL="gemma4:31b-cloud"
DEFAULT_PROXY="socks5://127.0.0.1:1080"
FRONT_PAGES=3   # 前几页
BACK_PAGES=3    # 后几页
DPI=150

# --- 视觉模型列表 ---
VISION_MODELS=(
    "gemma4:31b-cloud"
    "gemini-3-flash-preview:cloud"
    "kimi-k2.6:cloud"
    "glm-5.1:cloud"
)

# --- 参数解析 ---
if [ $# -lt 1 ]; then
    echo "用法: $0 <PDF 文件路径> [视觉模型名称] [--no-proxy|-np]"
    echo ""
    echo "视觉模型选项:"
    for m in "${VISION_MODELS[@]}"; do
        echo "   - $m"
    done
    echo ""
    echo "例如: $0 pdf/test-6.pdf gemma4:31b-cloud"
    exit 1
fi

PDF_INPUT="$1"
MODEL=""
USE_PROXY="true"

for arg in "${@:2}"; do
    if [ "$arg" = "--no-proxy" ] || [ "$arg" = "-np" ] || [ "$arg" = "noproxy" ]; then
        USE_PROXY="false"
    elif [[ "$arg" == *cloud* ]] || [[ "$arg" == *:latest ]]; then
        MODEL="$arg"
    fi
done

if [ -z "$MODEL" ]; then
    echo "=========================================================================="
    echo "💡 请选择视觉分析模型 (需支持图片输入):"
    echo "=========================================================================="
    echo " 1) gemma4:31b-cloud       (默认) - Google 最新开源多模态，图文理解极强"
    echo " 2) gemini-3-flash-preview:cloud  - Google 超快速，支持海量图片解析"
    echo " 3) kimi-k2.6:cloud               - 月之暗面，中英双语视觉理解出众"
    echo " 4) glm-5.1:cloud                 - 智谱旗舰，中文学术文档识别精准"
    echo "=========================================================================="
    read -p "请输入选择 [1-4] (默认 1): " choice
    case "$choice" in
        2) MODEL="gemini-3-flash-preview:cloud" ;;
        3) MODEL="kimi-k2.6:cloud" ;;
        4) MODEL="glm-5.1:cloud" ;;
        *) MODEL="gemma4:31b-cloud" ;;
    esac
fi

if [ ! -f "$PDF_INPUT" ]; then
    echo "错误: 找不到 PDF 文件 '$PDF_INPUT'"
    exit 1
fi

if ! command -v pdftoppm &> /dev/null; then
    echo "错误: 需要 pdftoppm (poppler)。请运行: brew install poppler"
    exit 1
fi

if ! command -v pdfinfo &> /dev/null; then
    echo "错误: 需要 pdfinfo (poppler)。请运行: brew install poppler"
    exit 1
fi

# 获取 PDF 总页数
TOTAL_PAGES=$(pdfinfo "$PDF_INPUT" 2>/dev/null | grep "^Pages:" | awk '{print $2}')
if [ -z "$TOTAL_PAGES" ] || [ "$TOTAL_PAGES" -lt 1 ]; then
    echo "错误: 无法读取 PDF 页数"
    exit 1
fi

# 计算后几页的起始页（不与前几页重叠）
BACK_START=$(( TOTAL_PAGES - BACK_PAGES + 1 ))
if [ "$BACK_START" -le "$FRONT_PAGES" ]; then
    BACK_START=$(( FRONT_PAGES + 1 ))
fi
# 如果总页数不够，从第 FRONT_PAGES+1 页开始
if [ "$BACK_START" -gt "$TOTAL_PAGES" ]; then
    BACK_START="$TOTAL_PAGES"
fi

[ "$USE_PROXY" = "false" ] && PROXY_STATUS="禁用" || PROXY_STATUS="启用 (${ALL_PROXY:-$DEFAULT_PROXY})"

echo "=========================================================="
echo "    🔍  PDF 视觉深度分析工具（首尾并行）"
echo "=========================================================="
echo " PDF 文件:  $PDF_INPUT"
echo " 总页数:    $TOTAL_PAGES 页"
echo " 视觉模型:  $MODEL"
echo " 前段分析:  第 1 ~ $FRONT_PAGES 页  → 模板 / 元数据"
echo " 后段分析:  第 $BACK_START ~ $TOTAL_PAGES 页 → 引用格式"
echo " 代理状态:  $PROXY_STATUS"
echo "=========================================================="

# --- Step 1: 提取图片（首页 + 末页）---
TMPDIR=$(mktemp -d)
trap "rm -rf '$TMPDIR'" EXIT

echo ""
echo ">>> [步骤 1/3] 提取 PDF 首尾页面为图片..."

# 提取前几页
pdftoppm -jpeg -r "$DPI" -f 1 -l "$FRONT_PAGES" "$PDF_INPUT" "$TMPDIR/front"

# 提取后几页
pdftoppm -jpeg -r "$DPI" -f "$BACK_START" -l "$TOTAL_PAGES" "$PDF_INPUT" "$TMPDIR/back"

# 整理前几页文件列表（排序取前 N 张）
FRONT_FILES=()
for f in "$TMPDIR"/front-*.jpg; do
    [ -f "$f" ] && FRONT_FILES+=("$f")
done
IFS=$'\n' FRONT_FILES=($(printf '%s\n' "${FRONT_FILES[@]}" | sort | head -n "$FRONT_PAGES"))
unset IFS

# 整理后几页文件列表
BACK_FILES=()
for f in "$TMPDIR"/back-*.jpg; do
    [ -f "$f" ] && BACK_FILES+=("$f")
done
IFS=$'\n' BACK_FILES=($(printf '%s\n' "${BACK_FILES[@]}" | sort | head -n "$BACK_PAGES"))
unset IFS

echo "    [前段] 提取 ${#FRONT_FILES[@]} 张: $(basename "${FRONT_FILES[@]}" | tr '\n' ' ')"
echo "    [后段] 提取 ${#BACK_FILES[@]} 张: $(basename "${BACK_FILES[@]}" | tr '\n' ' ')"

if [ ${#FRONT_FILES[@]} -eq 0 ] && [ ${#BACK_FILES[@]} -eq 0 ]; then
    echo "错误: 未能提取任何图片"
    exit 1
fi

# --- Step 2: 并行调用两个 LLM 任务 ---
echo ""
echo ">>> [步骤 2/3] 并行发送首页(模板分析) + 末页(引用分析) 给 $MODEL..."

# 并行启动两个后台 Python 进程
python3 "$SCRIPT_DIR/scripts/vision_inspect.py" --mode front "$MODEL" "${FRONT_FILES[@]}" \
    > "$TMPDIR/front_output.txt" 2> "$TMPDIR/front_log.txt" &
PID_FRONT=$!

python3 "$SCRIPT_DIR/scripts/vision_inspect.py" --mode back "$MODEL" "${BACK_FILES[@]}" \
    > "$TMPDIR/back_output.txt" 2> "$TMPDIR/back_log.txt" &
PID_BACK=$!

echo "    [front PID=$PID_FRONT] 首页分析已启动..."
echo "    [back  PID=$PID_BACK] 末页分析已启动..."
echo "    等待两路分析完成（并行进行中）..."

# 等待两个任务都结束
wait $PID_FRONT
STATUS_FRONT=$?
wait $PID_BACK
STATUS_BACK=$?

# 输出进度日志
[ -s "$TMPDIR/front_log.txt" ] && cat "$TMPDIR/front_log.txt"
[ -s "$TMPDIR/back_log.txt"  ] && cat "$TMPDIR/back_log.txt"

# --- Step 3: 输出合并结果 ---
echo ""
echo "=========================================================="
echo "📄 首页分析结果  —  LaTeX 模板 & 元数据"
echo "=========================================================="
if [ $STATUS_FRONT -eq 0 ] && [ -s "$TMPDIR/front_output.txt" ]; then
    cat "$TMPDIR/front_output.txt"
else
    echo "❌ 首页分析失败 (exit code $STATUS_FRONT)"
fi

echo ""
echo "=========================================================="
echo "📚 末页分析结果  —  引用 / 参考文献格式"
echo "=========================================================="
if [ $STATUS_BACK -eq 0 ] && [ -s "$TMPDIR/back_output.txt" ]; then
    cat "$TMPDIR/back_output.txt"
else
    echo "❌ 末页分析失败 (exit code $STATUS_BACK)"
fi

echo ""
echo "=========================================================="
if [ $STATUS_FRONT -eq 0 ] && [ $STATUS_BACK -eq 0 ]; then
    echo "✅ 首尾并行分析全部完成！"
else
    echo "⚠️  部分分析失败，请检查上方输出"
    exit 1
fi
echo "=========================================================="
