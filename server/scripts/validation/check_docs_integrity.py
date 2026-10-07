from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
BAD_PATTERNS = [
    'ansible/vault.yml',
    'ansible/vars/main.yml',
    'TODO-link-secao-11.1-original',
]
link_re = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
errors = []

for md in DOCS.rglob('*.md'):
    text = md.read_text(encoding='utf-8')
    for bad in BAD_PATTERNS:
        if bad in text:
            errors.append(f'{md.relative_to(ROOT)}: referência inválida -> {bad}')
    for link in link_re.findall(text):
        if link.startswith(('http://', 'https://', '#', 'mailto:')):
            continue
        clean = link.split('#', 1)[0]
        if not clean:
            continue
        target = (md.parent / clean).resolve()
        if not target.exists():
            errors.append(f'{md.relative_to(ROOT)}: link quebrado -> {link}')

if errors:
    print('ERROS ENCONTRADOS:')
    for item in errors:
        print('-', item)
    sys.exit(1)

print('OK: links relativos e caminhos sensíveis revisados.')
