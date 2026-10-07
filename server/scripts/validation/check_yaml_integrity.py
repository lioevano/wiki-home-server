from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    ROOT / 'mkdocs.yml',
    ROOT / 'ansible',
    ROOT / 'docker',
    ROOT / 'terraform',
]

errors = []

for target in TARGETS:
    files = [target] if target.is_file() else list(target.rglob('*.yml')) + list(target.rglob('*.yaml'))
    for file in files:
        try:
            text = file.read_text(encoding='utf-8')
            # mkdocs.yml uses a python tag in pymdownx.superfences; compose() validates syntax without constructing objects
            yaml.compose(text)
        except Exception as exc:
            errors.append(f'{file.relative_to(ROOT)}: {exc}')

if errors:
    print('ERROS YAML ENCONTRADOS:')
    for err in errors:
        print('-', err)
    sys.exit(1)

print('OK: sintaxe YAML válida nos arquivos verificados.')
