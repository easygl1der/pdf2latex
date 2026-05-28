import unittest
from pathlib import Path

from core.pdf_fix import fix_all


class PdfFixTests(unittest.TestCase):
    def test_spaced_roman_commands(self):
        text = (
            r"$\mathrm { l i n e a r }$ "
            r"$\mathrm { - o r b i t s }$ "
            r"$\mathrm { ~ a n d ~ }$"
        )

        fixed = fix_all(text)

        self.assertIn(r"\(\mathrm{linear}\)", fixed)
        self.assertIn(r"\(\mathrm{-orbits}\)", fixed)
        self.assertIn(r"\(\mathrm{~and~}\)", fixed)

    def test_adjacent_math_segments(self):
        text = r"The cell $B / B \cong$ $\mathbb { C } ^ { n }$ is affine."

        fixed = fix_all(text)

        self.assertIn(
            r"\(B / B \cong \mathbb{C}^{n}\)",
            fixed,
        )
        self.assertNotIn(r"$\mathbb", fixed)

    def test_latex_math_spacing(self):
        text = (
            r"$\mathfrak { S } _ { w } ( \mathbf { x } ; \mathbf { y } )$ "
            r"$\operatorname { F l } _ { n } ( \mathbb { C } )$ "
            r"$\operatorname* { m i n } \mathrm { D e s } ( v )$"
        )

        fixed = fix_all(text)

        self.assertIn(r"\(\mathfrak{S}_{w}(\mathbf{x}; \mathbf{y})\)", fixed)
        self.assertIn(r"\(\operatorname{Fl}_{n}(\mathbb{C})\)", fixed)
        self.assertIn(r"\(\operatorname*{min}\mathrm{Des}(v)\)", fixed)

    def test_unicode_math_noise(self):
        text = r"Let Φ be roots and γ ∈ Φ. Also $\pi + \tau + \beta$."

        fixed = fix_all(text)

        self.assertIn(r"\(\Phi\)", fixed)
        self.assertIn(r"\(\gamma\)", fixed)
        self.assertIn(r"\(\in\)", fixed)
        self.assertIn(r"\(\pi + \tau + \beta\)", fixed)

    def test_section_headings(self):
        text = "2.1. A refined Graham positivity. Let G be a group."

        fixed = fix_all(text)

        self.assertEqual(
            fixed,
            "## 2.1. A refined Graham positivity.\n\nLet G be a group.",
        )

    def test_math_delimiters(self):
        text = "Inline $x + y$.\n\n$$\nx = y\n$$"

        fixed = fix_all(text)

        self.assertIn(r"Inline \(x + y\).", fixed)
        self.assertIn("\\[\nx = y\n\\]", fixed)
        self.assertNotIn("$", fixed)

    def test_fix_all_is_idempotent_on_sample_output(self):
        sample = Path("output/test/test.md")
        if not sample.exists():
            self.skipTest("sample output/test/test.md does not exist")

        once = fix_all(sample.read_text(encoding="utf-8"))
        twice = fix_all(once)
        third = fix_all(twice)

        self.assertEqual(once, twice)
        self.assertEqual(twice, third)


if __name__ == "__main__":
    unittest.main()
