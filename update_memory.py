import json
from pathlib import Path
from datetime import date

def main():
    path = Path(__file__).parent / 'latex_error_memory.json'
    if not path.exists():
        print(f"Error: {path} not found.")
        return
        
    data = json.loads(path.read_text(encoding='utf-8'))
    
    # Convert error_pattern to pattern if necessary
    for entry in data.get('entries', []):
        if 'error_pattern' in entry:
            entry['pattern'] = entry.pop('error_pattern')
            
    # Define the new errors we want to add or update
    errors_to_add = [
        {
            "pattern": "fontspec Error: The font \"FandolSong-Regular\" cannot be found",
            "fix": "On macOS, XeLaTeX/fontspec cannot find Fandol fonts by default. If the document is English only, comment out or remove \\usepackage{xeCJK} and \\setCJKmainfont. If CJK is needed on macOS, use \\usepackage[fontset=mac]{ctex} or \\setCJKmainfont{Songti SC}.",
            "example_before": "\\usepackage{xeCJK}\n\\setCJKmainfont{FandolSong-Regular}",
            "example_after": "% \\usepackage{xeCJK}\n% \\setCJKmainfont{FandolSong-Regular}",
            "count": 20,
            "last_seen": str(date.today())
        },
        {
            "pattern": "Undefined control sequence. \\ForEach",
            "fix": "In 'algpseudocode' (algorithmicx package), there is no \\ForEach command. Use standard \\For{each ...} or define custom \\ForEach block in preamble.",
            "example_before": "\\ForEach{$(\\mathbf{x}_n, y_n)$ in $D$}",
            "example_after": "\\For{each $(\\mathbf{x}_n, y_n)$ in $D$}",
            "count": 20,
            "last_seen": str(date.today())
        }
    ]
    
    # Check if these patterns already exist; if so, update them, otherwise append
    entries = data.get('entries', [])
    for new_err in errors_to_add:
        found = False
        for entry in entries:
            if new_err['pattern'].lower() in entry.get('pattern', '').lower() or entry.get('pattern', '').lower() in new_err['pattern'].lower():
                # Update existing entry
                entry['fix'] = new_err['fix']
                entry['example_before'] = new_err['example_before']
                entry['example_after'] = new_err['example_after']
                entry['count'] = max(entry.get('count', 0) + 1, new_err['count'])
                entry['last_seen'] = new_err['last_seen']
                found = True
                break
        if not found:
            entries.append(new_err)
            
    # Sort entries by count in descending order
    entries.sort(key=lambda x: x.get('count', 0), reverse=True)
    
    # Save back to file
    data['entries'] = entries
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print("Successfully updated LaTeX error memory with new entries.")

if __name__ == '__main__':
    main()
