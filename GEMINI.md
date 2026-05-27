# Project Instructions: pdf2latex (Lite)

## Core Mandates
- **Language:** All code, comments, docstrings, and LLM prompts MUST be written in English.
- **Conversion Engine:** Use `MinerUConverter` from `scripts/mineru_convert.py`.
- **Execution Rule:** **DO NOT** run `python main.py` or any primary execution scripts inside the Gemini CLI. The user will handle all execution externally.
- **Verification Rule:** Before proposing or finalizing code changes, perform a thorough **theoretical logic check**. Ensure the code is syntactically correct, handles paths properly, and follows the simplified architecture.
- **Prompting Rule:** When providing prompts to LLMs, keep them simple, concise, and efficient. Avoid redundant instructions and prioritize clear, direct commands.
- **Philosophy:** Keep it simple. Avoid over-engineering, complex repair loops, or excessive abstractions. Prioritize direct, readable, and maintainable code.

## Workflows
1. **Simplified Pipeline:** Markdown -> Chapter Split -> LaTeX Conversion -> Assembly -> Simple Compilation.
2. **Manual Handoff:** After updating code, confirm the changes are logically sound and wait for the user to run the script.
3. **No Hidden Logic:** Ensure all processing steps are explicit in the nodes and easy to debug.
