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
        import time
        t0 = time.time()
        content = Path(markdown_path).read_text(encoding="utf-8")
        title = Path(markdown_path).stem
        
        print(f"\n[1/4] Analyzing Structure...")
        chapters = self._split_chapters(content)
        t1 = time.time()
        print(f"  - Found {len(chapters)} sections. ({t1-t0:.2f}s)")

        print(f"\n[2/4] Converting Fragments & Bib (Parallel)...")
        # Use ThreadPoolExecutor for speed
        # Reduced workers to 4 to avoid overloading the local proxy/Ollama
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Task 1: Fragments
            global_context = content[:1000] 
            future_to_ch = {
                executor.submit(self._convert_fragment, ch['content'], ch['title'], global_context): ch 
                for ch in chapters
            }

            
            # Task 2: Bibliography (Parallel with fragments)
            bib_future = executor.submit(self._extract_bibliography, content)
            
            results = []
            for future in concurrent.futures.as_completed(future_to_ch):
                ch = future_to_ch[future]
                try:
                    body = future.result()
                    results.append({"index": chapters.index(ch), "body": body})
                    print(f"    ✓ Done: {ch['title']}")
                except Exception as exc:
                    print(f"    ❌ Failed: {ch['title']} - {exc}")
            
            bib_content = bib_future.result()

        t2 = time.time()
        print(f"  - Fragment conversion finished. ({t2-t1:.2f}s)")

        # Sort back to original order
        results.sort(key=lambda x: x["index"])
        full_body = "\n".join(r["body"] for r in results)

        if bib_content:
            (output_dir / "refs.bib").write_text(bib_content, encoding="utf-8")
            print("  - Generated refs.bib")

        print(f"\n[3/4] Assembling & Repairing...")
        final_latex = self._assemble(title, full_body, bool(bib_content))
        final_latex = self._surgical_repair(final_latex)
        t3 = time.time()
        print(f"  - Assembly finished. ({t3-t2:.2f}s)")
        
        main_tex = output_dir / "main.tex"
        main_tex.write_text(final_latex, encoding="utf-8")
        
        return main_tex

    def _split_chapters(self, content: str) -> List[Dict[str, str]]:
        matches = list(re.finditer(r'^#\s+(.+)$', content, re.MULTILINE))
        if not matches:
            return [{"title": "Main", "content": content}]
        
        raw_chapters = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(content)
            raw_chapters.append({
                "title": m.group(1).strip(),
                "content": content[start:end].strip()
            })
        
        # Optimization: Merge small chapters (under 500 chars) into the next one
        merged = []
        current = None
        for ch in raw_chapters:
            if current is None:
                current = ch
            elif len(current["content"]) < 500:
                current["title"] += " and " + ch["title"]
                current["content"] += "\n\n" + ch["content"]
            else:
                merged.append(current)
                current = ch
        if current:
            merged.append(current)
        
        return merged

    def _convert_fragment(self, fragment: str, title: str, global_context: str = "") -> str:
        # Optimization: Only send context if fragment is large or complex
        ctx_inject = f"Context: {global_context}\n\n" if len(fragment) > 1000 else ""
        
        system = f"Markdown to LaTeX body for {self.template['name']} ({self.mode}). Return ONLY body content."
        user = f"{ctx_inject}Section: {title}\nContent:\n{fragment}"
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
        
        # 2. Fix unclosed environments
        envs = ["itemize", "enumerate", "figure", "table", "align", "equation"]
        for env in envs:
            opens = latex.count(f"\\begin{{{env}}}")
            closes = latex.count(f"\\end{{{env}}}")
            if opens > closes:
                latex += f"\n\\end{{{env}}}" * (opens - closes)
        
        # 3. Escape '&' in sections (common when merging)
        # Match \section{... & ...} and replace & with \&
        def escape_amp(m):
            return m.group(0).replace('&', r'\&')
        latex = re.sub(r'\\section\{[^}]*&[^}]*\}', escape_amp, latex)

        return latex
