#!/bin/bash
# ==============================================================================
# XeLaTeX 自动化编译与错误诊断引擎 (compile_latex.sh)
#
# 这是一个高可用的 LaTeX 自动化编译脚本，支持 nonstop 编译、SyncTeX 追溯、
# BibTeX 文献处理以及高精度的编译错误 Log 解析提取。
#
# 💡 使用场景案例与例子:
#   ./compile_latex.sh output/test-6/test-6.tex
#
# 🛠️ 编译工作流机制:
#   1. 初始化首次试译（Test Pass）：
#      在 -interaction=nonstopmode -synctex=1 模式下编译一次，产生 .log 文件。
#   2. 高精度日志解析与错误中断：
#      调用内置 Python 引擎，精准扫描 .log 文件，提取所有以 '!' 起始的多行编译
#      错误控制台信息（彻底忽略所有常规 warning），展示后直接退出。
#   3. 标准三Pass与文献编译（Success Pass）：
#      若首次试译无报错，则启动标准完整文献编译流（xelatex -> bibtex -> xelatex -> xelatex），
#      保证交叉引用、图表序号、目录和 BibTeX 文献完美渲染。
#
# ==============================================================================

# 检查输入参数
if [ $# -lt 1 ]; then
    echo "用法: $0 <LaTeX 文件路径 (.tex)>"
    echo "例如: $0 output/test-6/test-6.tex"
    exit 1
fi

TEX_FILE="$1"
if [ ! -f "$TEX_FILE" ]; then
    echo "错误: 找不到 LaTeX 文件 '$TEX_FILE'"
    exit 1
fi

DIR=$(dirname "$TEX_FILE")
BASENAME=$(basename "${TEX_FILE%.tex}")
LOG_FILE="$DIR/${BASENAME}.log"
AUX_FILE="$DIR/${BASENAME}.aux"

echo "=========================================================="
echo "    📊  正在启动 XeLaTeX 编译与错误分析引擎"
echo "=========================================================="
echo " LaTeX 文件: $TEX_FILE"
echo " 输出目录:   $DIR/"
echo "=========================================================="

# Step 1: 首次试译 (Test Compilation in nonstopmode)
echo ""
echo ">>> [步骤 1/3] 正在运行首次试译检测错误..."
set +e # 临时关闭 set -e，以便捕获 xelatex 退出码
xelatex -synctex=1 -interaction=nonstopmode -output-directory="$DIR" "$TEX_FILE" >/dev/null 2>&1
set -e

# Step 2: 使用内置 Python 高精度扫描并输出错误日志 (忽略 warning)
echo ">>> [步骤 2/3] 正在使用内置 Python 引擎进行高精日志排错分析..."

# 导出 LOG_FILE 路径供 python 读取，防止特殊字符报错
export TARGET_LOG_FILE="$LOG_FILE"

set +e # 必须临时关闭 set -e，否则如果 python3 返回 1 退出，bash 会立即终止脚本，无法执行下方的 $STATUS 判断
ERROR_REPORT=$(python3 -c "
import sys, os, re
log_path = os.environ.get('TARGET_LOG_FILE', '')
if not os.path.exists(log_path):
    print(f'未找到编译日志文件: {log_path}')
    sys.exit(1)

try:
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
except Exception as e:
    print(f'读取日志文件失败: {e}')
    sys.exit(1)

errors = []
in_error = False
current_error = []

for line in lines:
    if line.startswith('! '):
        if current_error:
            errors.append(''.join(current_error))
        current_error = [line]
        in_error = True
    elif in_error:
        # LaTeX 错误块到空行或遇到下一个特定块标志结束
        if line.strip() == '' or line.startswith('Here is how much of'):
            errors.append(''.join(current_error))
            current_error = []
            in_error = False
        else:
            current_error.append(line)
if current_error:
    errors.append(''.join(current_error))

if errors:
    print('\n'.join(errors))
    sys.exit(1) # 存在错误，非零退出
else:
    sys.exit(0) # 无错误，零退出
" 2>&1)
STATUS=$?
set -e

# 如果 Python 检查发现报错 (退出码非零)
if [ $STATUS -ne 0 ]; then
    echo ""
    echo "=========================================================="
    echo "❌ 发现 LaTeX 编译语法错误 (已忽略 warning):"
    echo "=========================================================="
    echo "$ERROR_REPORT"
    echo "=========================================================="
    echo "编译失败！请修复上述错误后再重新编译。"
    echo "=========================================================="
    exit 1
fi

echo ">>> [步骤 2/3] 恭喜！首轮试译通过，没有检测到任何编译错误。"

# Step 3: 若无报错，执行标准的 3-Pass 编译与 BibTeX 整合
echo ""
echo ">>> [步骤 3/3] 正在运行标准完整文献编排流水线..."

echo "    [Pass 1] 运行 BibTeX 生成参考文献目录..."
set +e
bibtex "$DIR/$BASENAME" >/dev/null 2>&1
set -e

echo "    [Pass 2] 运行 XeLaTeX 链接参考文献引用..."
xelatex -synctex=1 -interaction=nonstopmode -output-directory="$DIR" "$TEX_FILE" >/dev/null 2>&1

echo "    [Pass 3] 运行 XeLaTeX 最终版面校验与序号对齐..."
xelatex -synctex=1 -interaction=nonstopmode -output-directory="$DIR" "$TEX_FILE" >/dev/null 2>&1

echo "=========================================================="
echo "✅ XeLaTeX 编译完成，文献与交叉引用全部渲染成功！"
echo " 成果目录: $DIR/"
echo " PDF 文件: $DIR/${BASENAME}.pdf"
echo "=========================================================="
