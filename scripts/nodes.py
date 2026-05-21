"""
LangGraph 节点：supervisor / dispatch / chapter_writer / retriever / assembler
"""

import json
import re
from pathlib import Path

from langgraph.types import Send

from .config import TEMPLATES, OUTPUT_DIR, Chapter, ChapterOutput, PipelineState, WriterInput
from .llm import call_llm


# ── 工具函数 ──────────────────────────────────────────────────

def _extract_json(raw: str):
    start = raw.find('{')
    if start == -1:
        return None
    for end in range(len(raw), start, -1):
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            continue
    return None


# ── Step 2: Supervisor ────────────────────────────────────────

def supervisor_node(state: PipelineState) -> dict:
    print(f"\n[Step 2] Supervisor 分析文档结构 (模型: {state['model_name']})")

    md_path = Path(state["markdown_path"])
    full_text = md_path.read_text(encoding="utf-8")
    lines = full_text.splitlines()
    total_lines = len(lines)
    print(f"  Markdown 总行数: {total_lines}")

    if total_lines <= 500:
        user = f"""分析以下 Markdown 文档，识别所有主要章节（一级 # 标题和二级 ## 标题）。
对每个章节，给出行号范围（line_start 是标题所在行，line_end 是下一标题前一行）。
只输出 JSON，格式：
{{"title": "...", "chapters": [{{"index": 1, "title": "...", "line_start": 1, "line_end": 25}}]}}
注意：line_start 和 line_end 都是从 1 开始的行号。

文档内容：
{full_text}"""
        raw = call_llm(state["model_name"],
                       "你是文档结构分析专家，只输出严格 JSON。",
                       user, temperature=0.1)
        parsed = _extract_json(raw)
        if parsed and parsed.get("chapters"):
            chapters = [
                Chapter(index=c["index"], title=c["title"],
                        line_start=c["line_start"], line_end=c["line_end"])
                for c in parsed["chapters"]
            ]
            title = parsed.get("title", md_path.stem)
            print(f"  文档标题: {title}")
            print(f"  识别章节: {len(chapters)} 个")
            for c in chapters:
                print(f"    [{c['index']}] {c['title']} (行 {c['line_start']}-{c['line_end']})")
            return {"doc_title": title, "chapters": chapters}
        print("  [警告] LLM 解析失败，回退到正则解析")

    print(f"  正则解析章节结构...")
    title_match = re.search(r'^#\s+(.+)$', full_text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_path.stem

    heading_pattern = re.compile(r'^(#{1,2})\s+(.+)$', re.MULTILINE)
    matches = list(heading_pattern.finditer(full_text))

    chapters = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        ch_title = m.group(2).strip()
        line_start = full_text[:m.start()].count('\n') + 1
        if i + 1 < len(matches):
            line_end = full_text[:matches[i+1].start()].count('\n') + 1
        else:
            line_end = total_lines
        if level == 1 and i == 0:
            continue
        chapters.append(Chapter(
            index=len(chapters) + 1,
            title=ch_title,
            line_start=line_start,
            line_end=line_end,
        ))

    if not chapters:
        chapters.append(Chapter(index=1, title=title,
                                line_start=1, line_end=total_lines))

    print(f"  文档标题: {title}")
    print(f"  识别章节: {len(chapters)} 个")
    for c in chapters:
        print(f"    [{c['index']}] {c['title']} (行 {c['line_start']}-{c['line_end']})")
    return {"doc_title": title, "chapters": chapters}


# ── Step 3: 并行分发 ──────────────────────────────────────────

def dispatch_chapters(state: PipelineState):
    print(f"\n[Step 3] 并行分发 {len(state['chapters'])} 个 Sub-Agent")
    return [
        Send("chapter_writer", {
            "chapter":       ch,
            "markdown_path": state["markdown_path"],
            "all_titles":    [c["title"] for c in state["chapters"]],
            "template_name": state["template_name"],
            "model_name":    state["model_name"],
        })
        for ch in state["chapters"]
    ]


# ── Step 3a: Chapter Writer ───────────────────────────────────

def chapter_writer_node(state: WriterInput) -> dict:
    ch = state["chapter"]
    tpl = TEMPLATES[state["template_name"]]
    print(f"  [Sub-Agent #{ch['index']}] 写作: {ch['title']} (行 {ch['line_start']}-{ch['line_end']})")

    lines = Path(state["markdown_path"]).read_text(encoding="utf-8").splitlines()
    content = "\n".join(lines[ch["line_start"] - 1 : ch["line_end"]])
    print(f"    内容长度: {len(content)} 字符")

    system = f"""你是专业的 LaTeX 排版助手。
将给定的章节内容转换为标准 LaTeX 格式的正文片段。

【模板风格要求】
{tpl['style_hint']}

【输出规则】
- 只输出 LaTeX 正文片段（从 \\section 开始，不含 \\documentclass）
- 数学公式务必用 $...$ 或 \\[...\\] 包裹
- 保留原文的定理、定义、例题等结构
- 末尾加注释 % === END CHAPTER {ch['index']} ===
"""
    user = f"""请将以下内容（第 {ch['index']} 章：{ch['title']}）转换为 LaTeX 正文片段。
全书章节（供上下文参考）：{', '.join(state['all_titles'])}

原始内容：
{content}"""

    latex_body = call_llm(state["model_name"], system, user, temperature=0.2)
    latex_body = re.sub(r'<think>.*?</think>', '', latex_body, flags=re.DOTALL)
    latex_body = re.sub(r'&lt;/?think&gt;', '', latex_body, flags=re.IGNORECASE)

    safe = re.sub(r'[^\w]', '_', ch['title'])[:25]
    sub_path = OUTPUT_DIR / f"ch{ch['index']:02d}_{safe}.tex"
    sub_path.write_text(latex_body, encoding="utf-8")

    return {"chapter_outputs": [{"index": ch["index"], "title": ch["title"],
                                  "latex_body": latex_body}]}


# ── Step 4: Retriever ─────────────────────────────────────────

def retriever_node(state: PipelineState) -> dict:
    print(f"\n[Step 4] Retriever 检查格式一致性")
    tpl = TEMPLATES[state["template_name"]]
    reviewed = []

    for ch in sorted(state["chapter_outputs"], key=lambda x: x["index"]):
        print(f"  检查 #{ch['index']}: {ch['title']}")
        user = f"""请检查以下 LaTeX 片段，确保符合模板要求，如有问题直接修正后输出。

检查项目：
□ 数学公式是否都正确用 $$ 或 \\[\\] 包裹？
□ 定理/定义/引理等是否用了正确的 LaTeX 环境？（{tpl['style_hint'][:80]}）
□ 章节层级是否用了 \\section / \\subsection？
□ 末尾是否有 % === END CHAPTER {ch['index']} ===？
□ 是否有裸露的特殊字符（&, %, #, _ 等）未被转义？

LaTeX 片段：
{ch['latex_body']}

输出修正后的完整片段。"""

        reviewed_body = call_llm(
            state["model_name"],
            "你是 LaTeX 格式审查专家，只负责检查和修正格式错误，不改变实质内容。",
            user, temperature=0.1,
        )
        reviewed.append({**ch, "latex_body": reviewed_body})

        safe = re.sub(r'[^\w]', '_', ch['title'])[:25]
        sub_path = OUTPUT_DIR / f"ch{ch['index']:02d}_{safe}_reviewed.tex"
        sub_path.write_text(reviewed_body, encoding="utf-8")

    return {"chapter_outputs": reviewed}


# ── Step 5: Assembler ─────────────────────────────────────────

def assembler_node(state: PipelineState) -> dict:
    print(f"\n[Step 5] 拼接 main.tex (模板: {state['template_name']})")
    tpl = TEMPLATES[state["template_name"]]

    sorted_ch = sorted(state["chapter_outputs"], key=lambda x: x["index"])

    body_parts = []
    for ch in sorted_ch:
        body_parts.append(f"\n% ===== 第 {ch['index']} 章: {ch['title']} =====\n")
        body_parts.append(ch["latex_body"])
        body_parts.append("\n")
    full_body = "\n".join(body_parts)

    preamble = tpl["preamble"].replace("__TITLE__", state["doc_title"])
    document = tpl["body_wrapper"].replace("__BODY__", full_body)
    final = preamble + document

    main_path = OUTPUT_DIR / "main.tex"
    main_path.write_text(final, encoding="utf-8")
    print(f"  ✓ main.tex ({len(final)} 字符)")
    print(f"  ✓ 包含 {len(sorted_ch)} 个章节")

    input_lines = [
        f"\\input{{ch{ch['index']:02d}_{re.sub(r'[^\\w]', '_', ch['title'])[:25]}_reviewed}}"
        for ch in sorted_ch
    ]
    modular_body = "\n".join(input_lines)
    modular_document = tpl["body_wrapper"].replace("__BODY__", modular_body)
    modular_final = preamble + modular_document
    (OUTPUT_DIR / "main_modular.tex").write_text(modular_final, encoding="utf-8")
    print(f"  ✓ main_modular.tex (\\input 版本)")

    return {"final_latex": str(main_path)}
