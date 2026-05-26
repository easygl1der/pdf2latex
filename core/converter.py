import re
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any
from .config import TEMPLATES, OUTPUT_ROOT
from .llm import LLMProvider

class NextGenConverter:
    def __init__(self, provider: LLMProvider, template_name: str, mode: str = "notes"):
        self.provider = provider
        self.template = TEMPLATES[template_name]
        self.mode = mode
        self.context_memory = ""

    def convert(self, markdown_path: str, output_dir: Path):
        content = Path(markdown_path).read_text(encoding="utf-8")
        title = Path(markdown_path).stem
        
        print(f"\n[1/4] Analyzing Structure...")
        chapters = self._split_chapters(content)
        print(f"  - Found {len(chapters)} sections.")

        print(f"\n[2/4] Converting Fragments (Parallel)...")
        # Use ThreadPoolExecutor for speed
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Provide global context (doc start) to help model maintain consistency
            global_context = content[:2000]
            future_to_ch = {
                executor.submit(self._convert_fragment, ch['content'], ch['title'], global_context): ch 
                for ch in chapters
            }
            results = []
            for future in concurrent.futures.as_completed(future_to_ch):
                ch = future_to_ch[future]
                try:
                    body = future.result()
                    results.append({"index": chapters.index(ch), "body": body})
                    print(f"    ✓ Done: {ch['title']}")
                except Exception as exc:
                    print(f"    ❌ Failed: {ch['title']} - {exc}")
        
        # Sort back to original order
        results.sort(key=lambda x: x["index"])
        full_body = "\n".join(r["body"] for r in results)

        print(f"\n[3/4] Handling Bibliography...")
        bib_content = self._extract_bibliography(content)
        if bib_content:
            (output_dir / "refs.bib").write_text(bib_content, encoding="utf-8")
            print("  - Generated refs.bib")

        print(f"\n[4/4] Assembling & Repairing...")
        final_latex = self._assemble(title, full_body, bool(bib_content))
        final_latex = self._surgical_repair(final_latex)
        
        main_tex = output_dir / "main.tex"
        main_tex.write_text(final_latex, encoding="utf-8")
        
        return main_tex

    def _split_chapters(self, content: str) -> List[Dict[str, str]]:
        matches = list(re.finditer(r'^#\s+(.+)$', content, re.MULTILINE))
        if not matches:
            return [{"title": "Main", "content": content}]
        
        chapters = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(content)
            chapters.append({
                "title": m.group(1).strip(),
                "content": content[start:end].strip()
            })
        return chapters

    def _convert_fragment(self, fragment: str, title: str, global_context: str = "") -> str:
        system = f"Convert Markdown to LaTeX body for {self.template['name']}. Mode: {self.mode}. Return ONLY the body content. Use standard LaTeX environments. Do NOT include preamble, documentclass, or document tags."
        user = f"Overall Doc Context:\n{global_context}\n\nTarget Section: {title}\n\nContent:\n{fragment}"
        res = self.provider.call(system, user)
        res = re.sub(r'```(?:latex)?\n?', '', res)
        res = re.sub(r'\n?```', '', res)
        
        # Surgical strip of preamble hallucination
        res = re.sub(r'\\documentclass\[.*\]\{.*\}', '', res)
        res = re.sub(r'\\usepackage\{.*\}', '', res)
        res = re.sub(r'\\begin\{document\}', '', res)
        res = re.sub(r'\\end\{document\}', '', res)
        
        # Avoid duplicate sections
        res_clean = res.strip()
        if res_clean.startswith("\\section") or res_clean.startswith("\\chapter"):
            return res_clean
        
        return f"\\section{{{title}}}\n{res_clean}"

    def _extract_bibliography(self, content: str) -> str:
        if "References" not in content and "参考文献" not in content:
            return ""
        system = "Extract references as BibTeX. Return ONLY raw BibTeX entries."
        res = self.provider.call(system, content[-4000:]) # Focus on end
        res = re.sub(r'```(?:bibtex|bib)?\n?', '', res)
        res = re.sub(r'\n?```', '', res)
        return res.strip()

    def _assemble(self, title: str, body: str, has_bib: bool) -> str:
        header = self.template["preamble"].replace("__TITLE__", title)
        if has_bib:
            body += "\n\\bibliographystyle{plain}\n\\bibliography{refs}\n"
        
        full = header + self.template["body_wrapper"].replace("__BODY__", body)
        return full

    def _surgical_repair(self, latex: str) -> str:
        """Basic regex-based cleanup for common hallucination errors."""
        # 1. Remove duplicate \begin{document} if model hallucinated it
        parts = latex.split(r'\begin{document}')
        if len(parts) > 2:
            latex = parts[0] + r'\begin{document}' + "".join(parts[1:]).replace(r'\begin{document}', '')
        
        # 2. Fix unclosed environments (very basic)
        envs = ["itemize", "enumerate", "figure", "table", "align", "equation"]
        for env in envs:
            opens = latex.count(f"\\begin{{{env}}}")
            closes = latex.count(f"\\end{{{env}}}")
            if opens > closes:
                latex += f"\n\\end{{{env}}}" * (opens - closes)
        
        return latex
