#!/bin/bash

# Default proxy configuration
DEFAULT_PROXY="socks5://127.0.0.1:1080"

# Supported models list
MODELS=(
    "gemma4:31b-cloud"
    "glm-5.1:cloud"
    "nemotron-3-super:cloud"
    "gemini-3-flash-preview:cloud"
    "kimi-k2.6:cloud"
    "deepseek-v4-flash:cloud"
)

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
    echo "  3. 指定模型:   $0 \"分析图片\" gemini-3-flash-preview:cloud ./test.jpg"
    echo ""
    echo "支持的模型:"
    for m in "${MODELS[@]}"; do
        echo "  - $m"
    done
    echo "=========================================================="
    exit 1
}

# 必须提供至少一个参数（提示词）
if [ $# -lt 1 ]; then
    usage
fi

PROMPT="$1"
MODEL_GIVEN=""
IMAGE=""
MODEL=""

# 智能识别命令行参数 $2 和 $3
for arg in "$2" "$3"; do
    if [ -z "$arg" ]; then
        continue
    fi
    if [ -f "$arg" ]; then
        # 如果是文件，绑定为图片
        IMAGE="$arg"
    else
        # 检查是否为已知模型
        for m in "${MODELS[@]}"; do
            if [ "$arg" = "$m" ]; then
                MODEL_GIVEN="$arg"
                break
            fi
        done
        # 如果不是已知模型但以 :cloud 结尾，也识别为模型
        if [ -z "$MODEL_GIVEN" ] && [[ "$arg" == *":cloud" ]]; then
            MODEL_GIVEN="$arg"
        fi
    fi
done

# 如果命令行中没有指定模型，则展示交互式菜单供用户选择
if [ -z "$MODEL_GIVEN" ]; then
    echo "=========================================================================="
    echo "💡 未在命令行中指定模型，请选择您想要运行的云端模型 (请输入对应的数字序号):"
    echo "=========================================================================="
    echo " 1) gemma4:31b-cloud (默认)"
    echo "    - [最大输入] 128K tokens"
    echo "    - [最大输出] 4K tokens"
    echo "    - [适用场景] Google 最新开源推理模型，逻辑思考和代码生成能力极其拔尖"
    echo ""
    echo " 2) glm-5.1:cloud"
    echo "    - [最大输入] 128K tokens"
    echo "    - [最大输出] 8K tokens"
    echo "    - [适用场景] 智谱最新旗舰双语模型，中文流畅度与文案功底非常强"
    echo ""
    echo " 3) nemotron-3-super:cloud"
    echo "    - [最大输入] 128K tokens"
    echo "    - [最大输出] 8K tokens"
    echo "    - [适用场景] NVIDIA 特别优化的超级模型，数学推导与硬核代码表现优异"
    echo ""
    echo " 4) gemini-3-flash-preview:cloud"
    echo "    - [最大输入] 1,000K (1M) tokens"
    echo "    - [最大输出] 8K tokens"
    echo "    - [适用场景] 谷歌新一代超快速轻量模型，支持海量长文本与图片深度解析"
    echo ""
    echo " 5) kimi-k2.6:cloud"
    echo "    - [最大输入] 200K tokens"
    echo "    - [最大输出] 8K tokens"
    echo "    - [适用场景] 月之暗面长文本标杆，专为超长学术文献研读与深度上下文而生"
    echo ""
    echo " 6) deepseek-v4-flash:cloud"
    echo "    - [最大输入] 64K tokens"
    echo "    - [最大输出] 8K tokens"
    echo "    - [适用场景] 深度求索高吞吐量极速 Flash 模型，反应敏捷，极速响应"
    echo "=========================================================================="
    
    # 获取用户输入
    read -p "请输入您的选择 [1-6] (默认 1): " choice
    
    case "$choice" in
        2) MODEL="glm-5.1:cloud" ;;
        3) MODEL="nemotron-3-super:cloud" ;;
        4) MODEL="gemini-3-flash-preview:cloud" ;;
        5) MODEL="kimi-k2.6:cloud" ;;
        6) MODEL="deepseek-v4-flash:cloud" ;;
        *) MODEL="gemma4:31b-cloud" ;; # 默认选 1
    esac
else
    MODEL="$MODEL_GIVEN"
fi

# 确保 Proxy 变量正确
PROXY="${ALL_PROXY:-$DEFAULT_PROXY}"

echo ""
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
