"""
Writer Engine: Implements the 'Skeleton + Injection' workflow.
"""

import re
from pathlib import Path
from .config import TEMPLATES

def create_skeleton(state: dict) -> str:
    """Creates a LaTeX document skeleton with placeholders for sections."""
    tpl = TEMPLATES[state["template_name"]]
    
    # Header
    preamble = tpl["preamble"].replace("__TITLE__", state["doc_title"])\
                              .replace("__AUTHOR__", state.get("doc_author", "Anonymous"))\
                              .replace("__DATE__", state.get("doc_date", "unknown"))
    
    # Body with placeholders
    body_parts = []
    if "chapters" in state and state["chapters"]:
        for ch in state["chapters"]:
            placeholder = f"\n% [SECTION_START: {ch['title']}] %\n"
            placeholder += f"% CONTENT_PLACEHOLDER_{ch['index']} %\n"
            placeholder += f"% [SECTION_END: {ch['title']}] %\n"
            body_parts.append(placeholder)
    else:
        # Fallback for single-writer mode (paper)
        body_parts.append("\n% [FULL_CONTENT_PLACEHOLDER] %\n")

    full_body = tpl["body_wrapper"].replace("__BODY__", "".join(body_parts))
    return preamble + full_body

def inject_content(skeleton: str, placeholder_key: str, content: str) -> str:
    """Surgically injects generated LaTeX into the skeleton, stripping wrappers if necessary."""
    # Clean the content (strip code blocks if model added them)
    content = re.sub(r"^```latex\n", "", content)
    content = re.sub(r"\n```$", "", content)
    
    # If the LLM generated a full document, extract only what's inside \begin{document}...\end{document}
    doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', content, re.DOTALL)
    if doc_match:
        content = doc_match.group(1).strip()
    else:
        # Just in case it included preamble stuff without \begin{document}
        content = re.sub(r'\\documentclass\[.*?\]\{.*?\}', '', content)
        content = re.sub(r'\\usepackage\[.*?\]\{.*?\}', '', content)
        content = re.sub(r'\\usepackage\{.*?\}', '', content)
    
    pattern = f"% {placeholder_key} %"
    if pattern in skeleton:
        return skeleton.replace(pattern, content)
    
    # Fallback to general content placeholder
    if "% [FULL_CONTENT_PLACEHOLDER] %" in skeleton:
        return skeleton.replace("% [FULL_CONTENT_PLACEHOLDER] %", content)
        
    return skeleton
