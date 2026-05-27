#!/bin/bash
# ==============================================================================
# PDF 转 LaTeX 完整流水线工具 (pdf2latex.sh)
#
# 这是一个全自动的 PDF -> LaTeX 管道工具，它有机融合了 run_mineru.sh 与 llm.sh
# 的核心功能。
#
# 工作流程:
#   1. 调用 run_mineru.sh：将高清 PDF 提取并修复为 Markdown（存放在 output/<basename>/）
#   2. 交互式选择模型：供用户选择最适合生成 LaTeX 的云端模型（展示输入/输出限制）
#   3. 交互式选择代理：选择是否启用 SOCKS5 代理路由。
#   4. 流水线组装：利用选定模型将 Markdown 内容转换为完整、可编译的 LaTeX 模板 (.tex)。
#   5. 净化 LaTeX 源码：自动检测并剥离 LLM 附带的 \`\`\`latex 代码块包裹符号。
#
# 💡 使用场景案例与例子:
#   ./pdf2latex.sh pdf/test-6.pdf
#   ./pdf2latex.sh pdf/test-6.pdf -np  (直连不走代理)
#
# ==============================================================================

# Exit immediately if any pipeline command fails
set -e

# 获取项目根目录，确保 PYTHONPATH 导入正确
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

DEFAULT_PROXY="socks5://127.0.0.1:1080"

# 支持的模型列表
MODELS=(
    "gemma4:31b-cloud"
    "glm-5.1:cloud"
    "nemotron-3-super:cloud"
    "gemini-3-flash-preview:cloud"
    "kimi-k2.6:cloud"
    "deepseek-v4-flash:cloud"
)

# 检查输入参数
if [ $# -lt 1 ]; then
    echo "用法: $0 <PDF 文件路径> [代理选项]"
    echo "例如: $0 pdf/test-6.pdf"
    exit 1
fi

PDF_FILE="$1"
if [ ! -f "$PDF_FILE" ]; then
    echo "错误: 找不到 PDF 文件 '$PDF_FILE'"
    exit 1
fi

# 1. 检查命令行中是否显式禁用了代理
USE_PROXY_DECIDED=""
TEMP_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--no-proxy" ] || [ "$arg" = "-np" ] || [ "$arg" = "noproxy" ]; then
        USE_PROXY_DECIDED="false"
    elif [ "$arg" = "--proxy" ] || [ "$arg" = "-p" ] || [ "$arg" = "proxy" ]; then
        USE_PROXY_DECIDED="true"
    else
        TEMP_ARGS+=("$arg")
    fi
done

BASENAME=$(basename "${PDF_FILE%.pdf}")
MD_FILE="output/${BASENAME}/${BASENAME}.md"
TEX_FILE="output/${BASENAME}/${BASENAME}.tex"

echo "=========================================================="
echo "    🚀  欢迎使用 PDF -> LaTeX 完整转换管道"
echo "=========================================================="
echo " PDF 文件: $PDF_FILE"
echo "=========================================================="

# Step 1: 运行 MinerU 提取 Markdown 并执行 pdf_fix 净化
echo ""
echo ">>> [步骤 1/4] 正在提取 PDF 文本并应用 pdf_fix 预处理..."
./run_mineru.sh "$PDF_FILE"

if [ ! -f "$MD_FILE" ]; then
    echo "错误: 未能生成 Markdown 预处理文件 '$MD_FILE'，管道终止。"
    exit 1
fi
echo ">>> [步骤 1/4] 预处理成功！已生成 Markdown 文件: $MD_FILE"

# Step 2: 交互式选择用于 LaTeX 转换的 LLM 模型
echo ""
echo "=========================================================================="
echo "💡 请选择您想要用于将 Markdown 转换为 LaTeX 的云端模型 (请输入数字序号):"
echo "=========================================================================="
echo " 1) nemotron-3-super:cloud (默认)"
echo "    - [最大输入] 256K tokens (NIM API 限制为 131K)"
echo "    - [最大输出] 128K tokens (NIM API 限制总量在 131K 内)"
echo "    - [适用场景] NVIDIA 超强优化模型，数学公式、物理符号和科技格式非常严谨"
echo ""
echo " 2) glm-5.1:cloud"
echo "    - [最大输入] 200K tokens (202,752)"
echo "    - [最大输出] 128K tokens (131,072)"
echo "    - [适用场景] 智谱最新旗舰双语模型，非常擅长中英双语科技文档排版"
echo ""
echo " 3) gemma4:31b-cloud"
echo "    - [最大输入] 256K tokens (262,144)"
echo "    - [最大输出] 32K tokens (32,768)"
echo "    - [适用场景] Google 最新开源推理模型，公式推导及 LaTeX 语法排版极其优秀"
echo ""
echo " 4) gemini-3-flash-preview:cloud"
echo "    - [最大输入] 1,000K (1M) tokens (1,048,576)"
echo "    - [最大输出] 64K tokens (65,536)"
echo "    - [适用场景] 谷歌新一代超快速轻量模型，如果文档篇幅极长，推荐此模型"
echo ""
echo " 5) kimi-k2.6:cloud"
echo "    - [最大输入] 256K tokens (262,144)"
echo "    - [最大输出] 32K tokens (32,768)"
echo "    - [适用场景] 月之暗面旗舰长文本模型，结构化梳理与大篇幅排版能力出众"
echo ""
echo " 6) deepseek-v4-flash:cloud"
echo "    - [最大输入] 1,000K (1M) tokens (1,048,576)"
echo "    - [最大输出] 384K tokens (393,216)"
echo "    - [适用场景] 深度求索高吞吐量极速 Flash 模型，反应敏捷，响应速度极快"
echo "=========================================================================="

read -p "请输入您的选择 [1-6] (默认 1): " choice

case "$choice" in
    2) MODEL="glm-5.1:cloud" ;;
    3) MODEL="gemma4:31b-cloud" ;;
    4) MODEL="gemini-3-flash-preview:cloud" ;;
    5) MODEL="kimi-k2.6:cloud" ;;
    6) MODEL="deepseek-v4-flash:cloud" ;;
    *) MODEL="nemotron-3-super:cloud" ;; # 默认选 1
esac

# Step 3: 交互式选择代理选项
if [ -z "$USE_PROXY_DECIDED" ]; then
    echo ""
    read -p "是否启用 SOCKS5 代理 ($DEFAULT_PROXY)? [y/n] (默认 y): " proxy_choice
    if [[ "$proxy_choice" =~ ^[nN]$ ]]; then
        USE_PROXY_DECIDED="false"
    else
        USE_PROXY_DECIDED="true"
    fi
fi

# 确立代理环境
if [ "$USE_PROXY_DECIDED" = "false" ]; then
    PROXY_STATUS="已禁用 (Direct Connection)"
    PROXY_VAL=""
else
    PROXY_VAL="${ALL_PROXY:-$DEFAULT_PROXY}"
    PROXY_STATUS="已启用 ($PROXY_VAL)"
fi

# Step 4: 将 Markdown 传入选定 LLM 转换为编译 LaTeX 源码
echo ""
echo ">>> [步骤 3/4] 正在使用模型 $MODEL 转换为标准的可编译 LaTeX 模板..."
echo "    [当前代理状态]: $PROXY_STATUS"

# 读取 Markdown 并建立完美无损的 LLM prompt 文件
PROMPT_FILE=$(mktemp)

cat << 'EOF' > "$PROMPT_FILE"
你是一个顶级的 LaTeX 排版专家。
你的任务是将下面由 PDF 提取出的 Markdown 文本，无损地转化为结构优美、符合学术规范的、完整的、可编译的 LaTeX 源代码。

【强制硬性要求】:
1. 必须输出一整个完整的、可直接进行编译的 LaTeX 源码。即开头必须是 \documentclass{article} (或适合该内容的样式)，结尾必须是 \end{document}。
2. 必须包含常用的科学包，例如：
   \usepackage{amsmath}
   \usepackage{amssymb}
   \usepackage{amsthm}
   \usepackage{graphicx}
   \usepackage{hyperref}
   \usepackage{booktabs}
3. 精准转换公式：将所有行内公式和块级公式转化为标准的 LaTeX math 环境（如 $...$, $$, \begin{equation} 等）。
4. 结构化目录：所有的 markdown 标题（#，##）转换为相应的 \section, \subsection。
5. 转换 Markdown 表格：必须把 markdown 纯文本表格完美转化为 LaTeX 中的 \begin{tabular} 结构，不要保留 markdown 表格原样。
6. 🚫【绝对禁用包裹符】🚫: 输出内容必须【仅有】LaTeX 源码本身。千万不要将输出内容包裹在 ```latex ... ``` 这种 markdown 代码块符号中！不要有任何前言或后记（例如"这是您的 LaTeX 源码："）。

【待转换的 Markdown 文本内容】:
==================================================
EOF

cat "$MD_FILE" >> "$PROMPT_FILE"

cat << 'EOF' >> "$PROMPT_FILE"
==================================================
EOF

# 运行 Python 客户端查询 Ollama API，获取干净的 LaTeX 源码输出 (避免终端 ANSI 动画与冗余日志污染文件)
if [ "$USE_PROXY_DECIDED" = "false" ]; then
    ALL_PROXY="" http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" python3 scripts/query_ollama.py "$MODEL" "$PROMPT_FILE" "$TEX_FILE"
else
    ALL_PROXY="$PROXY_VAL" HTTP_PROXY="$PROXY_VAL" HTTPS_PROXY="$PROXY_VAL" http_proxy="$PROXY_VAL" https_proxy="$PROXY_VAL" python3 scripts/query_ollama.py "$MODEL" "$PROMPT_FILE" "$TEX_FILE"
fi

rm -f "$PROMPT_FILE"

# Step 5: 剥离可能伴随的 ```latex 代码块标签 (后处理双层保险)
echo ""
echo ">>> [步骤 4/4] 正在对生成的 LaTeX 代码进行高精净化 (剥离 Markdown 包裹标签)..."

python3 -c "
import sys, re
p = sys.argv[1]
content = open(p, encoding='utf-8').read().strip()

# 1. 彻底去除 DeepSeek 或其他模型输出的 <think>...</think> 推理内容
content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

# 2. 彻底去除可能存留的 Thinking... done thinking. 文本
content = re.sub(r'(?i)thinking\s*\.\.\..*?done\s*thinking\.?', '', content, flags=re.DOTALL).strip()

# 3. 剥离 Markdown 代码块包裹标签 (\`\`\`latex ... \`\`\`)
lines = content.splitlines()
if len(lines) > 0 and lines[0].strip().startswith('\`\`\`'):
    lines = lines[1:]
if len(lines) > 0 and lines[-1].strip().startswith('\`\`\`'):
    lines = lines[:-1]

cleaned = '\n'.join(lines).strip()
open(p, 'w', encoding='utf-8').write(cleaned)
" "$TEX_FILE"

echo ">>> [步骤 4/4] 净化完成！"
echo ""
echo "=========================================================="
echo "✅ 转换流水线圆满完成！"
echo " 转换后 LaTeX 目录: output/${BASENAME}/"
echo " LaTeX 主文件路径:  $TEX_FILE"
echo " (提示: 已为您生成标准的完整 LaTeX 代码，目前并未对其进行编译。)"
echo "=========================================================="
