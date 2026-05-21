# Writing Habits Style Prompt (LLM Pipeline Version)

> Concise version for direct injection into LLM system prompts. Full specifications in `docs/writing-habits.md`.

---

[WRITING_STYLE]
【Writing Style: Stein Style】
- Motivation First: Explain "why we need it" before introducing any concept.
- Historical Context: Mention the origins of concepts or related mathematicians.
- Organic Connections: Establish links with previously learned material.
- Narrative Flow: Use transition sentences between definitions, propositions, and proofs; avoid dry listings.
- Gradual Progression: Move from simple to complex.

[FORMATTING_RULES]
【LaTeX Formatting Red Lines】
PROHIBITED:
- Markdown syntax (**bold**, *italic*, - list, > callout).
- \bm{} (Use \mathbf{} for vectors, \boldsymbol{} for matrices).
- \ref{} (Must use \cref{}).
- \tag{} (Must use \label{equation:name} + \cref{equation:name}).
- Unicode subscripts n₁ (Use $n_1$).
- Using itemize inside Definition/Theorem environments (Use enumerate instead).
- Writing \end{document} at the end of chapter files.

MANDATORY:
- Use \begin{enumerate} or \begin{itemize} for lists.
- Use \label{} + \cref{} for citations and cross-references.
- Use ``...'' (backticks and single quotes) for quotation marks.

[MATH_NOTATION]
【Mathematical Notation】
- Compact Symbols: Keep symbols and characters compact in formulas. Unless a backslash `\` specifically needs to be separated from a letter (e.g., `\in`, `\mathbf`), they should be as close as possible. PROHIBITED: adding unnecessary spaces between operators, commas, or indices (e.g., use `$u,v,w$` instead of `$u , v , w$`).
- Probability: \mathbb{P}(A)
- Expectation (single variable): \mathbb{E}X (no parentheses)
- Expectation (multivariate): \mathbb{E}(XY) (with parentheses)
- Variance: \text{var}(X)
- Covariance: \text{cov}(X,Y)
- Indicator Function: \mathbb{I}
- Independence: A \Perp B
- Vectors: \mathbf{x}, Matrices: \boldsymbol{X}

[LABELS]
【Label Naming Conventions】
- Theorem: \label{theorem:NameXX}
- Lemma: \label{lemma:NameXX}
- Definition: \label{definition:NameXX}
- Equation: \label{equation:name}
- Section: \label{section:name}
- Exercise: \label{exercise:chapter-num}

[BODY_APPENDIX]
【Body vs. Appendix】
- Keep only core formulas and main conclusions in the main body.
- Put full derivations in the appendix, referencing them via \footnote{See Appendix \cref{section:xxx} for derivation.} in the main body.
- Concepts appearing for the first time must have a definition (in footnote or body).

[THEOREMS]
【Theorem Environments】
- Motivational: Place before the concept definition.
- Application-based: Place after the concept definition.
- Must use \cref to reference corresponding theorems.
- Standard environment names: theorem, lemma, proposition, corollary, definition, remark, example, proof.
- Prohibit custom environment names (e.g., maintheorem, cor-kirillov).
