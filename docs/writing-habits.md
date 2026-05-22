# Writing Style and Habits Specification (Agent Behavioral Guide)

> This document integrates 15+ scattered files into a single authoritative reference for Agents generating LaTeX content in the pdf2latex project.

---

## Part 1: Writing Philosophy and Style

### Core Philosophy

The essence of learning is deep understanding through dialogue, thinking, and writing. The purpose of notes is to **understand the context and logic** rather than rote memorization. Keep the main body focused on key results; move lengthy derivations to the appendix to avoid distraction.

### Stein Writing Style (Mandatory)

Mimic the narrative style of Stein's *Fourier Analysis* and *Complex Analysis*:

| Principle | Description |
|-----------|-------------|
| Motivation First | Explain "why we need this concept" and "where it comes from" before introducing it. |
| Historical Context | Focus on the origin and historical development of concepts. |
| Organic Connections | Emphasize the interconnectedness between different mathematical fields. |
| Narrative Flow | Use coherent narratives between definitions, propositions, and proofs; avoid dry listings. |
| Gradual Progression | Move from simple to complex; do not introduce technical details too early. |

### Six Concept Introduction Modes

**Mode 1: Starting from Physical/Practical Problems**
1. Describe observable physical phenomena or practical problems.
2. Build a mathematical model.
3. Lead to the core mathematical question.
4. Formalize the definition.

**Mode 2: Natural Extension of Known Content**
1. Review learned concepts.
2. Point out difficulties encountered in direct extension.
3. Introduce new conditions/definitions to resolve difficulties.
4. Explain why the condition is "natural."

**Mode 3: From Categorization to Generalization**
1. Start with the most specific examples.
2. Gradually relax conditions and introduce more general categories.
3. Provide typical examples for each category.
4. Finally, introduce the most general definition.

**Mode 4: Opening with Famous Quotes**
1. Quote a mathematician (typically 2-4 lines).
2. Explain the connection between the quote and the chapter content.
3. Outline the chapter structure.

**Mode 5: Cross-field Connections**
1. Explain the link between this topic and previously learned content.
2. Explain why this application is "natural" or "important."
3. Give specific examples of the application.

**Mode 6: Categorical Progression**
1. State a "general principle."
2. Arrange categories in order (simple to complex).
3. Explain each category sequentially.

### Common Transition Phrases

| Category | Expression |
|----------|------------|
| Motivation | The problem consists of... |
| Motivation | This leads us to... |
| Motivation | The key observation is... |
| Motivation | A natural question arises... |
| History | The sweeping development of... is due to... |
| History | ...was the first to... |
| Principle | There is a general principle... |
| Principle | At the heart of... lies... |
| Condition | A moment's reflection suggests... |
| Condition | The reliance on... is a device that allows us to... |
| Proof | We claim that... |
| Proof | It suffices to show that... |

---

## Part 2: LaTeX Formatting Specifications

### Absolute Prohibitions

| Prohibited | Correct Alternative |
|------------|---------------------|
| `**bold**` (Markdown Bold) | `\textbf{bold}` |
| `*italic*` (Markdown Italic) | `\textit{italic}` |
| `- list` (Markdown List) | `\begin{itemize}` or `\begin{enumerate}` |
| `> [!note]` (Obsidian Callout) | `\begin{note}...\end{note}` |
| ` ``` ` (Markdown Code Block) | `\begin{verbatim}` or `\texttt{}` |
| `\bm{x}` (Vector) | `\mathbf{x}` |
| `\bm{X}` (Matrix) | `\boldsymbol{X}` |
| `\I` (Indicator Function) | `\mathbb{I}` |
| `$n₁$` (Unicode Subscript) | `$n_1$` |
| `\tag{}` (Hard-coded Equation Number) | `\label{equation:name}` + `\cref{equation:name}` |
| `\ref{}` (Bare Reference) | `\cref{}` (using cleveref package) |
| `\include` (Chapter Inclusion) | `\input` |
| `\end{document}` in chapter files | **Absolutely Prohibited** (it truncates subsequent chapters) |
| `itemize` inside Definition/Theorem | Use `enumerate`; separate conditions with semicolons |

### Mandatory Usage

- Lists: `\begin{enumerate}...\end{enumerate}` or `\begin{itemize}...\end{itemize}`
- Bold: `\textbf{text}`
- Italic: `\textit{text}`
- Code: `\begin{verbatim}...\end{verbatim}` or `\texttt{text}`
- References: `\label{}` + `\cref{}`
- Footnotes: `\footnote{}`
- HTML `<details>` and `<summary>`: Convert to `\paragraph*{<summary_text>}` or a `remark` environment. Discard HTML/CSS and format inner content normally (e.g., Markdown tables become `\begin{table}`).

### Chinese Punctuation (for multilingual contexts)

- Use `` `` ... '' '' (backticks + single quotes) for quotation marks.

---

## Part 3: Mathematical Notation Specifications

### Probability and Statistics (Highest Priority)

| Concept | Symbol | LaTeX Command | Description |
|---------|--------|---------------|-------------|
| Probability | ℙ | `\mathbb{P}(A)` | Blackboard Bold P |
| Expectation (Single) | 𝔼X | `\mathbb{E}X` | No parentheses |
| Expectation (Multi) | 𝔼(XY) | `\mathbb{E}(XY)` | With parentheses |
| Variance | var | `\text{var}(X)` | Upright font |
| Covariance | cov | `\text{cov}(X,Y)` | Upright font |
| Correlation | corr | `\text{corr}(X,Y)` | Upright font |
| Independence | ⊥⊥ | `$A \Perp B$` | Double vertical bar |
| Indicator Function | 𝕀 | `\mathbb{I}` | Blackboard Bold I |
| p-value | p | `\text{p}_{}` | Empty subscript |

### Notation Consistency

| Concept | ✅ Unified | ❌ Prohibited |
|---------|-----------|---------------|
| Probability | `\mathbb{P}` | `P`, `Pr`, `p` |
| Expectation | `\mathbb{E}` | `E`, `Exp` |
| Variance | `\text{var}` | `Var`, `\mathrm{Var}` |
| Vector | `\mathbf{x}` | `\bm{x}`, `\vec{x}` |
| Matrix | `\boldsymbol{X}` | `\bm{X}` |

---

## Part 4: Theorem Environment Specifications

### Labeling Conventions

| Type | Format | Example |
|------|--------|---------|
| Def/Thm | `\label{definition:NameXX}` | `\label{theorem:NeymanTheorem}` |
| Lemma | `\label{lemma:NameXX}` | `\label{lemma:Neyman}` |
| Section | `\label{section:name}` | `\label{section:introduction}` |
| Equation | `\label{equation:name}` | `\label{equation:ATE}` |
| Figure | `\label{figure:name}` | `\label{figure:dag-example}` |
| Exercise | `\label{exercise:chapter-num}` | `\label{exercise:5-1}` |

### Example Environment (Motivation First)

Example must use `\cref` to reference corresponding theorems.

---

## Part 5: Body and Appendix Allocation

### Core Principle

Maintain narrative flow in the main body; move complete derivations to the appendix.

---

## Part 6: Citations and Footnotes

- Concepts appearing for the first time must have a supplemental definition in a footnote or the appendix.

---

## Part 7: Notes Directory Structure

```
notes/<topic>/
├── <topic>-notes.tex      # Main entry point (NOT main.tex)
├── compile.sh             # Compilation script
├── chapters/
│   ├── chapter0.tex       # Literature Overview (Mandatory)
│   ├── chapter1.tex
│   └── ...
└── appendix/
    └── qa.tex             # Q&A Records (Mandatory)
```

---

## Part 8: Compilation Specifications

### Compilation Command

Must use `compile.sh` from each directory (xelatex, 3 times).

```bash
#!/bin/bash
FILE="topic-notes"
for i in 1 2 3; do
    xelatex -synctex=1 -interaction=nonstopmode "$FILE.tex" > /dev/null 2>&1
done
```
