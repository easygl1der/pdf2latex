#!/bin/bash
# ==============================================================================
# Ollama LLM 终端助手工具 (llm.sh)
#
# 这是一个多功能的 Ollama 命令行客户端包装工具，支持智能参数识别、多模型交互式菜单
# 以及极其灵活的代理切换（走代理 / 不走代理 / 交互询问）。
#
# 💡 主要使用场景案例与例子:
#
# 1. 常规快速问答 (默认使用 SOCKS5 代理)
#    ./llm.sh "用 Python 写一个快速排序"
#
# 2. 结合本地图片进行多模态分析 (默认使用 SOCKS5 代理 + 智能参数顺序识别)
#    ./llm.sh "分析这张图片里的公式" ./test.jpg
#
# 3. 指定模型并直接运行 (免去交互式菜单，模型参数与图片参数顺序任意)
#    ./llm.sh "解释量子纠缠" gemini-3-flash-preview:cloud
#    ./llm.sh "这张图画了什么" gemini-3-flash-preview:cloud ./test.jpg
#
# 4. 彻底禁用代理进行直连 (用于局域网内部接口或直连国内 API)
#    - 方式 A (使用短参数):   ./llm.sh "你好" -np
#    - 方式 B (使用长参数):   ./llm.sh "你好" --no-proxy
#    - 方式 C (结合图片直连): ./llm.sh "识别图中的文字" ./test.jpg -np
#    - 方式 D (使用环境变量): USE_PROXY=false ./llm.sh "本地连接测试"
#
# 5. 全局覆盖默认代理地址 (使用外部代理服务器)
#    ALL_PROXY="socks5://192.168.1.100:7890" ./llm.sh "你好"
#
# ==============================================================================

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
    echo "  $0 <提示词/Prompt> [模型名称] [图片路径] [代理选项]"
    echo ""
    echo "智能参数自动识别及代理配置示例:"
    echo "  1. 仅提示词 (默认使用代理):"
    echo "     $0 \"你好，请自我介绍\""
    echo ""
    echo "  2. 不使用代理 (使用 -np 或 --no-proxy 标志):"
    echo "     $0 \"本地局域网问答\" -np"
    echo ""
    echo "  3. 提示词+图片+不使用代理:"
    echo "     $0 \"这张图里有什么？\" ./test.jpg --no-proxy"
    echo ""
    echo "  4. 环境变量控制代理:"
    echo "     USE_PROXY=false $0 \"快捷问答\""
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

# 1. 检查环境变量 USE_PROXY
USE_PROXY_DECIDED=""
if [ "$USE_PROXY" = "false" ]; then
    USE_PROXY_DECIDED="false"
elif [ "$USE_PROXY" = "true" ]; then
    USE_PROXY_DECIDED="true"
fi

# 2. 从命令行参数中提取代理控制标志 (--no-proxy, -np, noproxy)
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

# 重新分配过滤后的位置参数
set -- "${TEMP_ARGS[@]}"

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
    echo "    - [适用场景] NVIDIA 特别优化的超级模型，数学推导与硬硬编码表现优异"
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
    
    # 获取用户输入模型
    read -p "请输入您的选择 [1-6] (默认 1): " choice
    
    case "$choice" in
        2) MODEL="glm-5.1:cloud" ;;
        3) MODEL="nemotron-3-super:cloud" ;;
        4) MODEL="gemini-3-flash-preview:cloud" ;;
        5) MODEL="kimi-k2.6:cloud" ;;
        6) MODEL="deepseek-v4-flash:cloud" ;;
        *) MODEL="gemma4:31b-cloud" ;; # 默认选 1
    esac

    # 如果没有在命令行/环境变量中显式决定代理状态，进行交互式提问
    if [ -z "$USE_PROXY_DECIDED" ]; then
        echo ""
        read -p "是否启用 SOCKS5 代理 ($DEFAULT_PROXY)? [y/n] (默认 y): " proxy_choice
        if [[ "$proxy_choice" =~ ^[nN]$ ]]; then
            USE_PROXY_DECIDED="false"
        else
            USE_PROXY_DECIDED="true"
        fi
    fi
else
    MODEL="$MODEL_GIVEN"
    # 非交互模式下，如果未做决定，默认启用代理
    if [ -z "$USE_PROXY_DECIDED" ]; then
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

echo ""
echo "========================================="
echo "⚙️  执行配置:"
echo "   提示词: \"$PROMPT\""
echo "   模型:   $MODEL"
if [ -n "$IMAGE" ]; then
echo "   图片:   $IMAGE"
fi
echo "   代理:   $PROXY_STATUS"
echo "========================================="
echo ">>> 正在启动 Ollama..."
echo ""

# 调用 Ollama
if [ "$USE_PROXY_DECIDED" = "false" ]; then
    # 彻底清空代理变量进行直连
    if [ -n "$IMAGE" ]; then
        ALL_PROXY="" http_proxy="" https_proxy="" ALL_PROXY="" HTTP_PROXY="" HTTPS_PROXY="" ollama run "$MODEL" "$IMAGE" "$PROMPT"
    else
        ALL_PROXY="" http_proxy="" https_proxy="" ALL_PROXY="" HTTP_PROXY="" HTTPS_PROXY="" ollama run "$MODEL" "$PROMPT"
    fi
else
    # 启用配置的代理
    if [ -n "$IMAGE" ]; then
        ALL_PROXY="$PROXY_VAL" HTTP_PROXY="$PROXY_VAL" HTTPS_PROXY="$PROXY_VAL" http_proxy="$PROXY_VAL" https_proxy="$PROXY_VAL" ollama run "$MODEL" "$IMAGE" "$PROMPT"
    else
        ALL_PROXY="$PROXY_VAL" HTTP_PROXY="$PROXY_VAL" HTTPS_PROXY="$PROXY_VAL" http_proxy="$PROXY_VAL" https_proxy="$PROXY_VAL" ollama run "$MODEL" "$PROMPT"
    fi
fi
