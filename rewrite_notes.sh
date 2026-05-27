#!/bin/bash
# ==============================================================================
# LaTeX 个人风格改写工具 (rewrite_notes.sh)
#
# 读取一个已有的 LaTeX 文件，结合 docs/style-prompt.md 中定义的个人写作习惯，
# 让 LLM 将其改写为符合个人阅读与写作风格的 LaTeX 笔记文件。
#
# 输出文件名: <原文件名>_notes.tex（与原文件同目录）
#
# 💡 使用方式:
#   ./rewrite_notes.sh output/test-6/test-6.tex
#   ./rewrite_notes.sh output/test-6/test-6.tex gemma4:31b-cloud
#   ./rewrite_notes.sh output/test-6/test-6.tex nemotron-3-super:cloud -np
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STYLE_FILE="$SCRIPT_DIR/docs/style-prompt.md"
DEFAULT_MODEL="nemotron-3-super:cloud"
DEFAULT_PROXY="socks5://127.0.0.1:1080"

# --- 参数解析 ---
if [ $# -lt 1 ]; then
    echo "用法: $0 <LaTeX 文件路径> [模型名称] [--no-proxy|-np]"
    echo "例如: $0 output/test-6/test-6.tex"
    exit 1
fi

TEX_INPUT="$1"
MODEL="${2:-$DEFAULT_MODEL}"
USE_PROXY="true"

# 检测 -np 参数（可在任意位置）
for arg in "$@"; do
    if [ "$arg" = "--no-proxy" ] || [ "$arg" = "-np" ] || [ "$arg" = "noproxy" ]; then
        USE_PROXY="false"
    fi
done

if [ ! -f "$TEX_INPUT" ]; then
    echo "错误: 找不到 LaTeX 文件 '$TEX_INPUT'"
    exit 1
fi

if [ ! -f "$STYLE_FILE" ]; then
    echo "错误: 找不到风格文件 '$STYLE_FILE'"
    exit 1
fi

# 推导输出路径: 同目录下 <basename>_notes.tex
INPUT_DIR="$(dirname "$TEX_INPUT")"
INPUT_BASE="$(basename "${TEX_INPUT%.tex}")"
TEX_OUTPUT="$INPUT_DIR/${INPUT_BASE}_notes.tex"

echo "=========================================================="
echo "    ✍️   LaTeX 个人风格改写工具"
echo "=========================================================="
echo " 输入文件: $TEX_INPUT"
echo " 输出文件: $TEX_OUTPUT"
echo " 使用模型: $MODEL  (temperature=0)"
echo "=========================================================="

# --- 读取风格说明（从 style-prompt.md 中提取代码块内容）---
STYLE_CONTENT=$(python3 << 'PYEOF'
with open('docs/style-prompt.md', encoding='utf-8') as f:
    lines = f.readlines()

# Find lines that are exactly ``` (the fence markers)
boundaries = [i for i, l in enumerate(lines) if l.strip() == '```']

# The main style body is the LAST fenced block (between last two boundaries)
if len(boundaries) >= 2:
    block = ''.join(lines[boundaries[-2]+1 : boundaries[-1]]).strip()
    print(block)
else:
    print(open('docs/style-prompt.md').read().strip())
PYEOF
)

# --- 构建 prompt ---
PROMPT_FILE=$(mktemp)

cat << 'PROMPT_EOF' > "$PROMPT_FILE"
You are rewriting a LaTeX document into a personal study notes style.
Rewrite the LaTeX source below following these style rules exactly.

Output ONLY raw LaTeX. No markdown fences, no explanations. Start with \documentclass, end with \end{document}.

Rules:
1. Preserve all mathematical content, theorems, definitions, and proofs — do not invent, omit, or summarize.
2. Rewrite narrative text to follow the Stein style: motivation first, historical context, organic connections, narrative flow between definitions and proofs.
3. Apply all LaTeX formatting rules: use \cref not \ref, \mathbf for vectors, \boldsymbol for matrices, \mathbb{P}/\mathbb{E}/\text{var} for probability notation.
4. Replace any \bm{}, \tag{}, raw markdown syntax, or unicode subscripts with the correct LaTeX equivalents.
5. Add \label{} to every theorem, lemma, definition, equation, and section using the naming convention: theorem:Name, lemma:Name, definition:Name, equation:name, section:name.

PROMPT_EOF

echo "" >> "$PROMPT_FILE"
echo "【My Style Specifications】" >> "$PROMPT_FILE"
echo "$STYLE_CONTENT" >> "$PROMPT_FILE"
echo "" >> "$PROMPT_FILE"
echo "【LaTeX Source to Rewrite】" >> "$PROMPT_FILE"
echo "==================================================" >> "$PROMPT_FILE"
cat "$TEX_INPUT" >> "$PROMPT_FILE"
echo "" >> "$PROMPT_FILE"
echo "==================================================" >> "$PROMPT_FILE"

# --- 调用 Ollama ---
echo ""
echo ">>> 正在调用 $MODEL 进行风格改写..."

if [ "$USE_PROXY" = "false" ]; then
    ALL_PROXY="" http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" \
        python3 "$SCRIPT_DIR/scripts/query_ollama.py" "$MODEL" "$PROMPT_FILE" "$TEX_OUTPUT"
else
    PROXY_VAL="${ALL_PROXY:-$DEFAULT_PROXY}"
    ALL_PROXY="$PROXY_VAL" HTTP_PROXY="$PROXY_VAL" HTTPS_PROXY="$PROXY_VAL" \
    http_proxy="$PROXY_VAL" https_proxy="$PROXY_VAL" \
        python3 "$SCRIPT_DIR/scripts/query_ollama.py" "$MODEL" "$PROMPT_FILE" "$TEX_OUTPUT"
fi

rm -f "$PROMPT_FILE"

# --- 后处理：剥离可能的代码块包裹 ---
python3 -c "
import re, sys
p = sys.argv[1]
content = open(p, encoding='utf-8').read().strip()
# 去除 <think>...</think>
content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
# 去除 Markdown 代码块
lines = content.splitlines()
if lines and lines[0].strip().startswith('\`\`\`'):
    lines = lines[1:]
if lines and lines[-1].strip().startswith('\`\`\`'):
    lines = lines[:-1]
cleaned = '\n'.join(lines).strip()
if not cleaned.startswith('\\\\documentclass'):
    print('Warning: output does not start with \\\\documentclass — check the output file manually.', file=sys.stderr)
open(p, 'w', encoding='utf-8').write(cleaned)
" "$TEX_OUTPUT"

echo ""
echo "=========================================================="
echo "✅ 风格改写完成！"
echo "   输出文件: $TEX_OUTPUT"
echo "=========================================================="
