#!/bin/bash
# ==============================================================================
# 模块化 PDF -> LaTeX 调度调度器 (pipeline_v2.sh)
#
# 该脚本作为超级调度器，完全基于调用现有的独立模块脚本:
#   1. run_mineru.sh      - PDF 提取与清理 (Markdown)
#   2. query_ollama.py    - LLM 核心转换 (LaTeX 源码生成)
#   3. compile_latex.sh   - LaTeX 自动化编译 (PDF 生成)
#
# 💡 特色功能:
#   - 缓存机制：默认跳过已完成的 MinerU 转换步骤。
#   - 强制刷新：使用 -f 或 --force 强制重新执行 MinerU 转换。
#   - 代理控制：支持 -np 禁用代理。
#
# 🚀 使用示例:
#   ./pipeline_v2.sh pdf/test-6.pdf -f
# ==============================================================================

set -e

# --- 配置 ---
DEFAULT_PROXY="socks5://127.0.0.1:1080"
DEFAULT_MODEL="nemotron-3-super:cloud"

# --- 参数解析 ---
if [ $# -lt 1 ]; then
    echo "用法: $0 <PDF路径> [选项]"
    echo "选项:"
    echo "  -f, --force     强制重新运行 MinerU 转换"
    echo "  -np, --no-proxy 禁用网络代理"
    echo "  -m <model>      指定 LLM 模型 (默认: $DEFAULT_MODEL)"
    exit 1
fi

PDF_PATH="$1"
shift

FORCE_RECONVERT="false"
USE_PROXY="true"
MODEL="$DEFAULT_MODEL"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force) FORCE_RECONVERT="true"; shift ;;
        -np|--no-proxy) USE_PROXY="false"; shift ;;
        -m) MODEL="$2"; shift 2 ;;
        *) shift ;;
    esac
done

BASENAME=$(basename "${PDF_PATH%.pdf}")
MD_FILE="output/${BASENAME}/${BASENAME}.md"
TEX_FILE="output/${BASENAME}/${BASENAME}.tex"

echo "========================================="
echo "   🚀 PDF -> LaTeX 模块化调度器 v2"
echo "========================================="
echo " 输入文件: $PDF_PATH"
echo " 转换模型: $MODEL"
echo " 强制刷新: $FORCE_RECONVERT"
echo "========================================="

# --- Step 1: 预处理 (调用 run_mineru.sh) ---
echo ""
echo ">>> [1/3] 执行预处理 (MinerU)..."
if [ "$FORCE_RECONVERT" = "false" ] && [ -f "$MD_FILE" ]; then
    echo "  [Cache] 命中缓存，跳过 MinerU 转换。"
else
    if [ "$FORCE_RECONVERT" = "true" ]; then
        echo "  [Force] 强制重新转换..."
    fi
    ./run_mineru.sh "$PDF_PATH"
fi

if [ ! -f "$MD_FILE" ]; then
    echo "❌ 错误: 未能获取到 Markdown 文件 $MD_FILE"
    exit 1
fi

# --- Step 2: LaTeX 转换 (调用脚本处理) ---
echo ""
echo ">>> [2/3] 执行 LaTeX 转换 (LLM)..."

# 构造 Prompt 文件
PROMPT_FILE=$(mktemp)
cat << 'EOF' > "$PROMPT_FILE"
You are a LaTeX format converter. Convert the Markdown below into a complete, compilable LaTeX source file.
Rules:
1. Output ONLY raw LaTeX. Start with \documentclass and end with \end{document}.
2. No preamble text, no explanations, no markdown code fences.
3. Include amsmath, amssymb, graphicx, booktabs, hyperref, fontspec, geometry.
4. Presere all content verbatim. Use section/subsection for headings.
5. Use proper LaTeX environments for math and tables.
EOF
cat "$MD_FILE" >> "$PROMPT_FILE"

# 执行转换
if [ "$USE_PROXY" = "false" ]; then
    ALL_PROXY="" http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" python3 scripts/query_ollama.py "$MODEL" "$PROMPT_FILE" "$TEX_FILE"
else
    ALL_PROXY="$DEFAULT_PROXY" HTTP_PROXY="$DEFAULT_PROXY" HTTPS_PROXY="$DEFAULT_PROXY" http_proxy="$DEFAULT_PROXY" https_proxy="$DEFAULT_PROXY" python3 scripts/query_ollama.py "$MODEL" "$PROMPT_FILE" "$TEX_FILE"
fi

rm -f "$PROMPT_FILE"

# 后处理：净化 LaTeX
python3 -c "
import sys, re
p = sys.argv[1]
content = open(p, encoding='utf-8').read().strip()
content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
lines = content.splitlines()
if len(lines) > 0 and lines[0].strip().startswith('\`\`\`'): lines = lines[1:]
if len(lines) > 0 and lines[-1].strip().startswith('\`\`\`'): lines = lines[:-1]
open(p, 'w', encoding='utf-8').write('\n'.join(lines).strip())
" "$TEX_FILE"

# --- Step 3: 编译 (调用 compile_latex.sh) ---
echo ""
echo ">>> [3/3] 执行自动化编译 (XeLaTeX)..."
./compile_latex.sh "$TEX_FILE"

echo ""
echo "========================================="
echo "✅ 任务圆满完成！"
echo " 输出目录: output/${BASENAME}/"
echo " PDF 文件: output/${BASENAME}/${BASENAME}.pdf"
echo "========================================="
