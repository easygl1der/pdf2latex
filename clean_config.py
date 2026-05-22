from pathlib import Path

def main():
    path = Path(__file__).parent / 'scripts' / 'config.py'
    if not path.exists():
        print(f"Error: {path} not found.")
        return
        
    content = path.read_text(encoding='utf-8')

    # A very specific search/replace for amsart to clean it up
    bad_amsart = r"""\documentclass{amsart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{fontspec}
\usepackage[fontset=mac, scheme=plain]{ctex}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{float}
\usepackage{multirow}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{hyperref}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{hyperref}
\usepackage{cleveref}"""

    good_amsart = r"""\documentclass{amsart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{fontspec}
\usepackage[fontset=mac, scheme=plain]{ctex}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{float}
\usepackage{multirow}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{hyperref}
\usepackage{cleveref}"""

    content = content.replace(bad_amsart, good_amsart)

    # Ensure multirow/algorithm in article template
    bad_article = r"""\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{float}
\usepackage{hyperref, xcolor, enumitem}
\usepackage{cleveref}"""

    good_article = r"""\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{float}
\usepackage{multirow}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{hyperref, xcolor, enumitem}
\usepackage{cleveref}"""

    content = content.replace(bad_article, good_article)

    path.write_text(content, encoding='utf-8')
    print("Cleaned config.py successfully.")

if __name__ == '__main__':
    main()
