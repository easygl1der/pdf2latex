#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# 获取项目根目录，确保 PYTHONPATH 导入正确
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

TOKEN="eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiIzNDQwMDc1MCIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3OTQ3MjE1OCwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiYTQ5NGZlODAtNjQ3NS00M2Y3LTk0M2YtNTUwMmM5Yzg5MWJhIiwiZW1haWwiOiIiLCJleHAiOjE3ODcyNDgxNTh9.0WWoAbya1E3mEZrOPUcb8bwGCoAKb4YoEJ7l7nlQHR_XHOaOrjXKEtdxy_FDoDHYxI8z2c6VZFYAKBfEp6WARg"

# 检查输入参数
if [ $# -lt 1 ]; then
    echo "用法: $0 <PDF 文件路径>"
    echo "例如: $0 pdf/test-6.pdf"
    exit 1
fi

PDF_FILE="$1"
if [ ! -f "$PDF_FILE" ]; then
    echo "错误: 找不到 PDF 文件 '$PDF_FILE'"
    exit 1
fi

BASENAME=$(basename "${PDF_FILE%.pdf}")
ZIP_FILE="${BASENAME}.zip"
OUTPUT_DIR="output/${BASENAME}"

# 确保 output 目录存在
mkdir -p output

echo "========================================="
echo "   MinerU 高清 PDF -> Markdown 转换工具"
echo "========================================="
echo "输入文件: $PDF_FILE"
echo "输出目录: $OUTPUT_DIR/"
echo "========================================="

# Step 1: 向 MinerU 注册并申请上传 URL
echo ">>> [1/5] 正在向 MinerU 申请上传地址..."
UPLOAD_RESP=$(curl -s -X POST 'https://mineru.net/api/v4/file-urls/batch' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"files": [{"name": "'"$(basename "$PDF_FILE")"'", "data_id": "test001"}], "model_version": "vlm"}')

# 检查是否成功获取 JSON
if echo "$UPLOAD_RESP" | grep -q '"code":0'; then
    BATCH_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['batch_id'])")
    UPLOAD_URL=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['file_urls'][0])")
    echo "申请成功: batch_id=$BATCH_ID"
else
    echo "错误: 申请上传地址失败，接口响应为:"
    echo "$UPLOAD_RESP"
    exit 1
fi

# Step 2: 上传本地 PDF 文件
echo ">>> [2/5] 正在上传 PDF 文件..."
curl -s -X PUT -T "$PDF_FILE" "$UPLOAD_URL"
echo "上传成功！"

# Step 3: 轮询解析结果
echo ">>> [3/5] 正在等待 MinerU 解析结果（轮询中，每7秒一次）..."
STATE="pending"
ZIP_URL=""

# 轮询上限为 60 次 (即 420 秒 / 7 分钟)
for i in $(seq 1 60); do
  sleep 7
  RESULT=$(curl -s -X GET "https://mineru.net/api/v4/extract-results/batch/$BATCH_ID" \
    -H "Authorization: Bearer $TOKEN")
  
  STATE=$(echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['extract_result']; print(r[0]['state'])" 2>/dev/null || echo "pending")
  echo "  [$i] 当前解析状态: $STATE"
  
  if [ "$STATE" = "done" ]; then
    ZIP_URL=$(echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['extract_result']; print(r[0]['full_zip_url'])")
    break
  elif [ "$STATE" = "failed" ]; then
    echo "错误: MinerU 解析失败！"
    echo "$RESULT"
    exit 1
  fi
done

if [ -z "$ZIP_URL" ]; then
    echo "错误: 解析超时或未能获取到结果下载链接。"
    exit 1
fi

# Step 4: 下载并解压结果
echo ">>> [4/5] 正在下载 MinerU 提取包..."
curl -L "$ZIP_URL" -o "$ZIP_FILE"
echo "下载成功，正在解包和重命名规范化文件..."

# 清空旧目录并解压
rm -rf "$OUTPUT_DIR"
unzip -q "$ZIP_FILE" -d "$OUTPUT_DIR"
rm -f "$ZIP_FILE"

# 重命名主 markdown 文件
if [ -f "${OUTPUT_DIR}/full.md" ]; then
    mv "${OUTPUT_DIR}/full.md" "${OUTPUT_DIR}/${BASENAME}.md"
else
    for md_file in "${OUTPUT_DIR}"/*.md; do
        if [ -f "$md_file" ]; then
            mv "$md_file" "${OUTPUT_DIR}/${BASENAME}.md"
            break
        fi
    done
fi

# 将其他伴生文件（如 json, layout, pdf）重命名
for file in "${OUTPUT_DIR}"/*; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        if [[ "$filename" == "${BASENAME}.md" ]]; then
            continue
        fi
        if [[ "$filename" == "layout.json" ]]; then
            mv "$file" "${OUTPUT_DIR}/${BASENAME}_layout.json"
            continue
        fi
        if [[ "$filename" == *"_"* ]]; then
            uuid="${filename%%_*}"
            new_filename="${filename/$uuid/$BASENAME}"
            mv "$file" "${OUTPUT_DIR}/$new_filename"
        fi
    fi
done

# 规范化最主要的 JSON 文件
if [ -f "${OUTPUT_DIR}/${BASENAME}_content_list.json" ]; then
    cp "${OUTPUT_DIR}/${BASENAME}_content_list.json" "${OUTPUT_DIR}/${BASENAME}.json"
elif [ -f "${OUTPUT_DIR}/${BASENAME}_model.json" ]; then
    cp "${OUTPUT_DIR}/${BASENAME}_model.json" "${OUTPUT_DIR}/${BASENAME}.json"
fi

# Step 5: 调用 core.pdf_fix 进行高精度 Markdown 清理
MD_FILE="${OUTPUT_DIR}/${BASENAME}.md"
if [ -f "$MD_FILE" ]; then
    echo ">>> [5/5] 正在运行 core.pdf_fix 清理并修复 LaTeX 格式与公式排版噪声..."
    PYTHONPATH="$PROJECT_ROOT" python3 -c "import sys; from core.pdf_fix import fix_all; p = sys.argv[1]; content = open(p, encoding='utf-8').read(); open(p, 'w', encoding='utf-8').write(fix_all(content))" "$MD_FILE"
    echo ">>> core.pdf_fix 清理修复成功！"
else
    echo "警告: 未能找到生成的 Markdown 主文件 '$MD_FILE'，跳过修复阶段。"
fi

echo "========================================="
echo "✅ 转换圆满完成！"
echo "结果目录: $OUTPUT_DIR/"
echo "Markdown 文件: ${OUTPUT_DIR}/${BASENAME}.md"
echo "JSON 结构化文件: ${OUTPUT_DIR}/${BASENAME}.json"
echo "========================================="
