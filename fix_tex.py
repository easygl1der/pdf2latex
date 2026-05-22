import re
import sys

with open('/Volumes/SSK SSD/Projects/pdf2latex/output/test-1/main.tex', 'r') as f:
    content = f.read()

# Replace \caption{ \begin{tabular} ... \end{tabular} } with just the tabular
pattern = r'\\caption\{\s*(\\begin\{tabular\}.*?\\end\{tabular\})\s*\}'
content = re.sub(pattern, r'\1', content, flags=re.DOTALL)

with open('/Volumes/SSK SSD/Projects/pdf2latex/output/test-1/main.tex', 'w') as f:
    f.write(content)

print("Fixed main.tex")
