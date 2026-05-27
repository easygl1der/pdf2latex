#!/bin/bash
# ==============================================================================
# PDF 首页视觉分析工具 (inspect_pdf.sh)
#
# 将 PDF 的前三页转换为图片，发送给视觉大模型，识别 LaTeX 模板类型及关键元数据。
# 输出包含模板信息、标题、作者、日期、机构等 \maketitle 所需的全部信息。
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
MAX_PAGES=3
DPI=150  # 分辨率：150dpi 足够 LLM 识别文字，同时控制 base64 大小

# --- 视觉模型列表（必须支持图片输入）---
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

# 从参数中识别模型和代理选项
for arg in "${@:2}"; do
    if [ "$arg" = "--no-proxy" ] || [ "$arg" = "-np" ] || [ "$arg" = "noproxy" ]; then
        USE_PROXY="false"
    elif [[ "$arg" == *cloud* ]] || [[ "$arg" == *:latest ]]; then
        # Match any model name containing "cloud" (e.g. gemma4:31b-cloud, gemini-3-flash-preview:cloud)
        MODEL="$arg"
    fi
done

# 未指定模型时交互选择
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

BASENAME=$(basename "${PDF_INPUT%.pdf}")
PROXY_VAL="${ALL_PROXY:-$DEFAULT_PROXY}"
[ "$USE_PROXY" = "false" ] && PROXY_STATUS="禁用" || PROXY_STATUS="启用 ($PROXY_VAL)"

echo "=========================================================="
echo "    🔍  PDF 首页视觉分析工具"
echo "=========================================================="
echo " PDF 文件: $PDF_INPUT"
echo " 视觉模型: $MODEL"
echo " 提取页数: 前 $MAX_PAGES 页 @ ${DPI}dpi"
echo " 代理状态: $PROXY_STATUS"
echo "=========================================================="

# --- Step 1: PDF 前三页 → JPG ---
TMPDIR=$(mktemp -d)
trap "rm -rf '$TMPDIR'" EXIT

echo ""
echo ">>> [步骤 1/3] 提取 PDF 前 $MAX_PAGES 页为图片..."
pdftoppm -jpeg -r "$DPI" -f 1 -l "$MAX_PAGES" "$PDF_INPUT" "$TMPDIR/page"

PAGE_FILES=()
for f in "$TMPDIR"/page-*.jpg "$TMPDIR"/page-*-*.jpg; do
    [ -f "$f" ] && PAGE_FILES+=("$f")
done

# 按文件名排序，只取前三张
IFS=$'\n' PAGE_FILES=($(printf '%s\n' "${PAGE_FILES[@]}" | sort | head -n "$MAX_PAGES"))
unset IFS

if [ ${#PAGE_FILES[@]} -eq 0 ]; then
    echo "错误: pdftoppm 未能生成图片文件，请检查 PDF 文件是否有效"
    exit 1
fi

echo ">>> 成功提取 ${#PAGE_FILES[@]} 张页面图片"
for f in "${PAGE_FILES[@]}"; do
    SIZE=$(du -sh "$f" 2>/dev/null | cut -f1)
    echo "    - $(basename "$f") ($SIZE)"
done

# --- Step 2: 图片 → Base64，调用视觉 API ---
echo ""
echo ">>> [步骤 2/3] 正在将图片编码并发送给 $MODEL..."

# 调用独立 Python 脚本（避免 heredoc 转义问题，urllib 不支持 socks5，Ollama 本地直连即可）
python3 "$SCRIPT_DIR/scripts/vision_inspect.py" "$MODEL" "${PAGE_FILES[@]}" > "$TMPDIR/llm_output.txt"
STATUS=$?

if [ $STATUS -ne 0 ]; then
    echo "错误: 视觉模型调用失败，请检查 Ollama 服务状态和模型名称"
    exit 1
fi

# --- Step 3: 输出结果 ---
echo ""
echo ">>> [步骤 3/3] 分析结果:"
echo "=========================================================="
cat "$TMPDIR/llm_output.txt"
echo ""
echo "=========================================================="
echo "✅ 分析完成！"
echo "=========================================================="
