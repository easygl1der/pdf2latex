"""
CrossRef API Tool: Search literature metadata based on title/author/key.
"""

import requests
import re
from typing import Optional, Dict, Any, List
import xml.etree.ElementTree as ET
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Configuration and Session Initialization ──────────────────────────

def get_session():
    """Create a Session with retry mechanism."""
    session = requests.Session()
    retries = Retry(
        total=10,
        backoff_factor=2.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

_SESSION = get_session()
_HEADERS = {
    "User-Agent": "pdf2latex/1.0 (mailto:admin@example.com)"
}

def search_crossref(query: str) -> Optional[Dict[str, Any]]:
    """Search for literature through the CrossRef API and retrieve metadata."""
    base_url = "https://api.crossref.org/works"
    clean_query = re.sub(r'[^a-zA-Z0-9\s]', ' ', query).strip()
    
    # Strategy: Try bibliographic search
    try:
        params = {"query.bibliographic": clean_query, "rows": 1}
        response = _SESSION.get(base_url, params=params, headers=_HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            items = data.get("message", {}).get("items", [])
            if items:
                return items[0]
    except Exception as e:
        print(f"  [CrossRef] Search exception: {e}")
    
    return None

def get_crossref_bibtex(doi: str) -> Optional[str]:
    """Retrieve standard BibTeX format using DOI through content negotiation."""
    url = f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex"
    try:
        response = _SESSION.get(url, headers=_HEADERS, timeout=10)
        if response.status_code == 200:
            return response.text.strip()
    except Exception:
        pass
    return None

def search_arxiv(query: str) -> Optional[Dict[str, Any]]:
    """Search for literature through the arXiv API."""
    clean_query = re.sub(r'[^a-zA-Z0-9\s]', ' ', query).strip().replace(' ', '+')
    url = f"http://export.arxiv.org/api/query?search_query=all:{clean_query}&start=0&max_results=1"
    
    try:
        response = _SESSION.get(url, timeout=15)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entry = root.find('atom:entry', ns)
            if entry is not None:
                title_elem = entry.find('atom:title', ns)
                if title_elem is None: return None
                title = title_elem.text.strip().replace('\n', ' ')
                authors = [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)]
                published = entry.find('atom:published', ns).text
                return {
                    "title": [title],
                    "author": [{"given": "", "family": a} for a in authors],
                    "issued": {"date-parts": [[int(published[:4])]]},
                    "DOI": entry.find('atom:id', ns).text.split('/')[-1],
                    "container-title": ["arXiv preprint"]
                }
    except Exception as e:
        print(f"  [arXiv] Search exception: {e}")
    return None

def format_bibitem(key: str, item: Dict[str, Any]) -> str:
    """Format search results as \\bibitem."""
    title = item.get("title", ["Unknown Title"])[0]
    authors_list = item.get("author", [])
    if authors_list:
        authors = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list])
    else:
        authors = "Unknown Author"
        
    pub = item.get("published-print") or item.get("published-online") or item.get("issued")
    year = ""
    if pub and "date-parts" in pub:
        year = pub["date-parts"][0][0]
    
    year_str = f", {year}" if year else ""
    container = item.get("container-title", [""])[0]
    journal_str = f" \\textit{{{container}}}" if container else ""
    
    doi = item.get("DOI", "")
    prefix = "arXiv:" if "arxiv" in str(item.get("container-title", "")).lower() else "doi:"
    doi_str = f" {prefix}{doi}" if doi else ""
    
    return f"\\bibitem{{{key}}} {authors}. {title}.{journal_str}{year_str}.{doi_str}"

def extract_citations(latex_text: str) -> List[str]:
    r"""Extract all keys from \cite{key1,key2}."""
    keys = []
    # Match \cite{key1, key2}
    matches = re.findall(r'\\cite\{([^}]+)\}', latex_text)
    for m in matches:
        # Split by comma and strip whitespace
        parts = [p.strip() for p in m.split(',')]
        keys.extend(parts)
    return sorted(list(set(keys)))

def extract_bibitems(latex_text: str) -> Dict[str, str]:
    r"""Extract all text content following \bibitem{key}."""
    items = {}
    # Match content after \bibitem{key} until the next \bibitem or end of environment
    pattern = re.compile(r'\\bibitem\{([^}]+)\}\s*(.*?)(?=\\bibitem|\\end\{thebibliography\}|$)', re.DOTALL)
    for m in pattern.finditer(latex_text):
        key = m.group(1).strip()
        content = m.group(2).strip()
        items[key] = content
    return items
