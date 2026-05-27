#!/bin/bash

# Default values
DEFAULT_MODEL="gemma4:31b-cloud"
DEFAULT_PROXY="socks5://127.0.0.1:1080"

# Help / Usage message
usage() {
    echo "=========================================================="
    echo "            Ollama LLM Client Helper Script               "
    echo "=========================================================="
    echo "用法:"
    echo "  $0 <提示词/Prompt> [模型名称] [图片路径]"
    echo ""
    echo "智能参数自动识别示例:"
    echo "  1. 仅提示词:   $0 \"你好，请自我介绍\""
    echo "  2. 提示词+图片: $0 \"这张图里有什么？\" ./test.jpg"
    echo "  3. 提示词+模型+图片: $0 \"分析图片\" gemma4:31b-cloud ./test.jpg"
    echo ""
    echo "环境变量配置 (可在外部覆盖):"
    echo "  ALL_PROXY     (默认: $DEFAULT_PROXY)"
    echo "  OLLAMA_MODEL  (默认: $DEFAULT_MODEL)"
    echo "=========================================================="
    exit 1
}

# 必须提供至少一个参数（提示词）
if [ $# -lt 1 ]; then
    usage
fi

PROMPT="$1"
MODEL=""
IMAGE=""

# 智能解析 positional arguments
if [ $# -eq 1 ]; then
    # 只有一个参数：提示词
    MODEL="${OLLAMA_MODEL:-$DEFAULT_MODEL}"
elif [ $# -eq 2 ]; then
    # 两个参数：提示词 + (模型 或 图片)
    if [ -f "$2" ]; then
        # 如果第二个参数是一个存在的文件，认定它是图片路径
        IMAGE="$2"
        MODEL="${OLLAMA_MODEL:-$DEFAULT_MODEL}"
    else
        # 否则认定它是模型名称
        MODEL="$2"
    fi
elif [ $# -ge 3 ]; then
    # 三个或更多参数：提示词 + 模型 + 图片 (顺序任意)
    if [ -f "$2" ]; then
        IMAGE="$2"
        MODEL="$3"
    elif [ -f "$3" ]; then
        MODEL="$2"
        IMAGE="$3"
    else
        MODEL="$2"
        IMAGE="$3"
    fi
fi

# 确保 Proxy 变量正确
PROXY="${ALL_PROXY:-$DEFAULT_PROXY}"

echo "========================================="
echo "⚙️  执行配置:"
echo "   提示词: \"$PROMPT\""
echo "   模型:   $MODEL"
if [ -n "$IMAGE" ]; then
echo "   图片:   $IMAGE"
fi
echo "   代理:   $PROXY"
echo "========================================="
echo ">>> 正在启动 Ollama..."
echo ""

# 调用 Ollama
if [ -n "$IMAGE" ]; then
    ALL_PROXY="$PROXY" ollama run "$MODEL" "$IMAGE" "$PROMPT"
else
    ALL_PROXY="$PROXY" ollama run "$MODEL" "$PROMPT"
fi
