# pdf2latex — PDF → LaTeX 自动转换工具

## 一句话介绍
给定任意 PDF（教材/论文/书籍），自动转换为指定模板的完整 LaTeX 文件。

## 架构
```
PDF 文件
  │
  ▼  Step 1: MinerU API
[转录节点] ──→ output/converted.md
  │
  ▼  Step 2: Supervisor Agent
[章节解析] ──→ [{index, title, content}, ...]
  │
  │  Send API 并行分发
  ├──→ [Sub-Agent 第1章] ──┐
  ├──→ [Sub-Agent 第2章] ──┤  按模板要求转 LaTeX
  └──→ [Sub-Agent 第N章] ──┤
                           │
  ▼  Step 4 (汇聚)         │
[Retriever] ←─────────────┘  格式一致性检查
  │
  ▼  Step 5
[Assembler] ──→ output/ch01_xxx.tex
            ──→ output/ch02_xxx.tex
            ──→ output/main.tex          (完整合并版)
            ──→ output/main_modular.tex  (\input 引用版)
```

## 安装
```bash
pip install -r requirements.txt
```

## 配置 API Key
```bash
export MINERU_API_KEY="你的 MinerU Key"     # 从 mineru.net 获取
export MINIMAX_API_KEY="你的 MiniMax Key"   # 从 minimax.chat 获取
# 可选，使用 OpenAI 模型时需要：
export OPENAI_API_KEY="你的 OpenAI Key"
```

## 使用方法

```bash
# 查看可用模板
python main.py --list-templates

# 使用 amsart 模板（数学论文风格）
python main.py mybook.pdf --template amsart

# 使用 ctexart 模板（中文教材风格）
python main.py mybook.pdf --template ctexart --model minimax

# 使用 article 模板 + OpenAI 模型
python main.py mybook.pdf --template article --model openai

# 生成 Beamer 幻灯片
python main.py mybook.pdf --template beamer
```

## 可用模板

| 模板名     | 适用场景           |
|------------|-------------------|
| `amsart`   | 数学论文/笔记      |
| `article`  | 通用文章/教材笔记  |
| `ctexart`  | 中文教材（中文优先）|
| `beamer`   | 演示文稿（幻灯片） |

## 添加自定义模板
在 `main.py` 的 `TEMPLATES` 字典中添加：
```python
"mytemplate": {
    "desc": "我的模板",
    "preamble": r"""\documentclass{...}
...
""",
    "body_wrapper": r"""\begin{document}
__BODY__
\end{document}
""",
    "style_hint": "告诉 AI 应该用什么环境和风格",
},
```

## 输出文件说明
- `output/converted.md`        — MinerU 转录的 Markdown（自动缓存，重复运行不重复调用 API）
- `output/ch01_xxx.tex`        — 各章节独立 tex 文件
- `output/ch01_xxx_reviewed.tex` — 经 Retriever 检查后的版本
- `output/main.tex`            — 完整合并文件（可直接编译）
- `output/main_modular.tex`    — 模块化版本（通过 \input 引用各章节）
