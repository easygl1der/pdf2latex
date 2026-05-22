### ROLE: SENIOR LATEX TYPESETTING EXPERT
Convert the following Markdown to a FULL and COMPLETE LaTeX document for the {{template_name}} style.

### MANDATORY METADATA (USE EXACTLY THESE):
- TITLE: {{doc_title}}
- AUTHOR: {{doc_author}}
- DATE: {{doc_date}}

### TARGET TEMPLATE STRUCTURE:
```latex
{{template_structure}}
```

### STYLE SPECIFICATIONS:
{{style_hint}}
{{style_prompt}}

### VISUAL CONTEXT FOR IMAGES:
{{visual_context}}

### CRITICAL CONSTRAINTS (MUST FOLLOW):
1. COMPACT MATH: All math formulas MUST have ZERO SPACES.
   - EXAMPLE: Use $a+b=c$, NOT $a + b = c$.
   - RULE: Zero spaces after \sum, \max, \int, and around +, -, =, ^, _, {, }.
2. EQUATION TAGGING: If a display math block ($$) contains a manual tag like (1), (2.1), etc., DO NOT use \tag{}. Instead, use the \begin{equation} environment with a \label{eq:number}.
3. CROSS-REFERENCES: Convert all plain-text references to equations (e.g., 'as seen in (1)') into proper LaTeX \ref{eq:1} commands.
4. ENVIRONMENT RULES: PROHIBITED: \begin{array} for equations. Use aligned/cases instead. PROHIBITED: Manual numbering like (7) except when converted to structural labels.
5. CITATIONS: Convert all plain-text citations like [18], [1, 2], or (Author, 2020) into proper LaTeX \cite{...} commands.
6. FULL DOCUMENT: You must generate everything from \documentclass to \end{document}.
7. CLEANLINESS: Ignore all CSS, HTML <style> tags, or original PDF page numbers.
8. OUTPUT: Return ONLY the final LaTeX code block.
