"""
Simple reflow utility to convert a single long-line text export into paragraph-separated text.
Heuristics used:
 - Insert blank line after sentence-ending punctuation (., ?, !) followed by space + uppercase (including Romanian diacritics).
 - Ensure numbered headings (e.g. "1.") start on a new line.
 - Turn sequences of multiple spaces into a single space.
 - Preserve existing double-newlines.

Usage:
  python tools\reflow_text.py <input.txt> [<output.txt>]
If output omitted, the input file will be overwritten after creating a backup `<input>.bak`.
"""
import sys
import re
from pathlib import Path

def reflow_text(text: str) -> str:
    # Normalize newlines
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # If there are many short lines already, assume it's OK
    lines = text.split('\n')
    avg_len = sum(len(l) for l in lines) / max(1, len(lines))
    if len(lines) > 30 and avg_len < 300:
        return text  # already reasonably broken

    # Collapse multiple spaces
    text = re.sub(r' {2,}', ' ', text)

    # 1) Insert newline (double) after sentence end if followed by space+uppercase (including Romanian diacritics)
    sentence_end_pattern = re.compile(r'([\.\?!])\s+(?=[A-ZÀÂĂÎȘȚ])', flags=re.UNICODE)
    text = sentence_end_pattern.sub(r'\1\n\n', text)

    # 2) Ensure numbered headings like '1.' '1)' or '1.' start on a new line
    text = re.sub(r'(?<!\n)(\s*)(\d{1,3}[\.)])', r'\n\2', text)

    # 3) Ensure hyphenated list items start on new lines
    text = re.sub(r'(?<!\n)\s*-\s+', '\n- ', text)

    # 4) Insert newline before uppercase headings (sequences of uppercase words)
    # Look for at least two uppercase words or a single long uppercase word (>=6 chars)
    def insert_before_headings(m):
        return ('\n\n' + m.group(0))
    heading_pattern = re.compile(r'(?<=\n|^)([A-ZĂÂÎȘȚ]{3,}(?:[ \t]+[A-ZĂÂÎȘȚ]{2,})+)|(?<=\n|^)([A-ZĂÂÎȘȚ]{6,})')
    text = heading_pattern.sub(insert_before_headings, text)

    # 5) Fix cases where a word boundary is missing and a lowercase is followed by uppercase without space (e.g. 'NERVOSPoate')
    text = re.sub(r'([a-zăâîșț])([A-ZĂÂÎȘȚ])', r'\1\n\2', text)

    # Replace multiple blank lines with two
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Trim leading/trailing whitespace
    text = text.strip() + '\n'
    return text


def main():
    if len(sys.argv) < 2:
        print('Usage: python tools\\reflow_text.py <input.txt> [<output.txt>]')
        return
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not inp.exists():
        print('Input file not found:', inp)
        return

    text = inp.read_text(encoding='utf-8')
    new = reflow_text(text)

    if out is None:
        bak = inp.with_suffix(inp.suffix + '.bak')
        inp.rename(bak)
        inp.write_text(new, encoding='utf-8')
        print(f'Overwrote {inp} (backup at {bak})')
    else:
        out.write_text(new, encoding='utf-8')
        print(f'Wrote reflowed text to {out}')

if __name__ == '__main__':
    main()
