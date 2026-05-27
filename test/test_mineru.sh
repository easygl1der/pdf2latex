#!/bin/bash

# 获取项目根目录，以便在任意路径下运行都能正确导入 core.pdf_fix
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TOKEN="eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiIzNDQwMDc1MCIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3OTQ3MjE1OCwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiYTQ5NGZlODAtNjQ3NS00M2Y3LTk0M2YtNTUwMmM5Yzg5MWJhIiwiZW1haWwiOiIiLCJleHAiOjE3ODcyNDgxNTh9.0WWoAbya1E3mEZrOPUcb8bwGCoAKb4YoEJ7l7nlQHR_XHOaOrjXKEtdxy_FDoDHYxI8z2c6VZFYAKBfEp6WARg"

# 支持从命令行参数传递 PDF 路径，默认为 demo.pdf
PDF_FILE="${1:-demo.pdf}"
BASENAME=$(basename "${PDF_FILE%.pdf}")

# Step 1: 如果本地不存在该 PDF，则下载；否则直接使用本地 PDF
if [ ! -f "$PDF_FILE" ]; then
  echo ">>> 本地未找到 $PDF_FILE，开始从 arXiv 下载..."
  curl -L 'https://arxiv.org/pdf/2310.18047' \
    -o "$PDF_FILE"
  echo "PDF 下载完成"
else
  echo ">>> 使用本地已存在的 PDF: $PDF_FILE"
fi

# Step 2: 向 MinerU 申请上传地址（直连，不走代理）
echo ""
echo ">>> 申请上传地址..."
UPLOAD_RESP=$(curl -s -X POST 'https://mineru.net/api/v4/file-urls/batch' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"files": [{"name": "'"$(basename "$PDF_FILE")"'", "data_id": "test001"}], "model_version": "vlm"}')

echo "响应: $UPLOAD_RESP"
BATCH_ID=$(echo $UPLOAD_RESP | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['batch_id'])")
UPLOAD_URL=$(echo $UPLOAD_RESP | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['file_urls'][0])")
echo "batch_id: $BATCH_ID"

# Step 3: 上传本地 PDF（直连）
echo ""
echo ">>> 上传 PDF..."
curl -s -X PUT -T "$PDF_FILE" "$UPLOAD_URL"
echo "上传完成"

# Step 4: 轮询结果（直连）
echo ""
echo ">>> 等待解析结果..."
for i in $(seq 1 30); do
  sleep 10
  RESULT=$(curl -s -X GET "https://mineru.net/api/v4/extract-results/batch/$BATCH_ID" \
    -H "Authorization: Bearer $TOKEN")
  STATE=$(echo $RESULT | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['extract_result']; print(r[0]['state'])" 2>/dev/null)
  echo "[$i] 状态: $STATE"
  if [ "$STATE" = "done" ]; then
    ZIP_URL=$(echo $RESULT | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['extract_result']; print(r[0]['full_zip_url'])")
    echo ""
    echo "✅ 解析完成！ZIP 下载地址："
    echo "$ZIP_URL"
    
    # 下载结果
    ZIP_FILE="${BASENAME}.zip"
    curl -L "$ZIP_URL" -o "$ZIP_FILE"
    echo "已下载为 $ZIP_FILE"
    
    echo ">>> 解压并重命名文件夹和文件..."
    rm -rf "${BASENAME}"
    unzip -q "$ZIP_FILE" -d "${BASENAME}"
    
    # 重命名内部的 .md 
    if [ -f "${BASENAME}/full.md" ]; then
        mv "${BASENAME}/full.md" "${BASENAME}/${BASENAME}.md"
    else
        # 兜底：如果不是 full.md，找第一个 md 重命名
        for md_file in "${BASENAME}"/*.md; do
            if [ -f "$md_file" ]; then
                mv "$md_file" "${BASENAME}/${BASENAME}.md"
                break
            fi
        done
    fi
    
    # 将内部所有的 json、pdf 等文件规范化命名
    for file in "${BASENAME}"/*; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            
            # 跳过已经重命名好的 md 文件
            if [[ "$filename" == "${BASENAME}.md" ]]; then
                continue
            fi
            
            # 特殊处理 layout.json (因为它没有下划线前缀)
            if [[ "$filename" == "layout.json" ]]; then
                mv "$file" "${BASENAME}/${BASENAME}_layout.json"
                continue
            fi
            
            # 找到 MinerU 随机 ID 开头的文件 (如 fc99c1fc-xxx_model.json)
            if [[ "$filename" == *"_"* ]]; then
                uuid="${filename%%_*}"
                # 把该 uuid 替换成 BASENAME (即 demo)
                new_filename="${filename/$uuid/$BASENAME}"
                mv "$file" "${BASENAME}/$new_filename"
            fi
        fi
    done
    
    # 为了满足“里面的 json 名字也与 pdf 名字一致”的需求
    # 我们挑一个最主要的结构化 json（content_list.json 或 model.json）复制为 demo.json
    if [ -f "${BASENAME}/${BASENAME}_content_list.json" ]; then
        cp "${BASENAME}/${BASENAME}_content_list.json" "${BASENAME}/${BASENAME}.json"
    elif [ -f "${BASENAME}/${BASENAME}_model.json" ]; then
        cp "${BASENAME}/${BASENAME}_model.json" "${BASENAME}/${BASENAME}.json"
    fi
    
    # 使用 core.pdf_fix 清理 md 内容
    MD_FILE="${BASENAME}/${BASENAME}.md"
    if [ -f "$MD_FILE" ]; then
        echo ">>> 使用 core.pdf_fix 清理 md 内容..."
        PYTHONPATH="$PROJECT_ROOT" python3 -c "import sys; from core.pdf_fix import fix_all; p = sys.argv[1]; content = open(p, encoding='utf-8').read(); open(p, 'w', encoding='utf-8').write(fix_all(content))" "$MD_FILE"
        echo "✅ md 内容清理完成！"
    fi

    echo "✅ 完成！结果存放在文件夹: ${BASENAME} 中，并且 md 和 json 已处理完毕"
    break
  elif [ "$STATE" = "failed" ]; then
    echo "❌ 解析失败"
    echo $RESULT
    break
  fi
done
