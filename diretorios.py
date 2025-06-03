import os
import yaml
import zipfile

MKDOCS_FILE = 'mkdocs.yml'
DOCS_DIR = 'docs'
ZIP_FILE = 'documentacao-vazia.zip'

def parse_nav(nav_section):
    paths = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for _, value in node.items():
                walk(value)
        elif isinstance(node, str):
            paths.append(node)  # Aqui usamos node, não "value"
    
    walk(nav_section)
    return paths

def ensure_docs_exist(md_paths):
    for rel_path in md_paths:
        full_path = os.path.join(DOCS_DIR, rel_path)
        dir_path = os.path.dirname(full_path)

        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        if not os.path.isfile(full_path):
            with open(full_path, 'w', encoding='utf-8') as f:
                title = os.path.basename(full_path).replace('-', ' ').replace('.md', '').capitalize()
                f.write(f'# {title}\n\n')
                print(f'[novo] Criado: {rel_path}')
        else:
            print(f'[ok] Já existe: {rel_path}')

def criar_zip(md_paths):
    with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for rel_path in md_paths:
            full_path = os.path.join(DOCS_DIR, rel_path)
            if os.path.isfile(full_path):
                zipf.write(full_path, arcname=os.path.join('docs', rel_path))
                print(f'[zip] Incluído: {rel_path}')
    print(f'\n✅ ZIP gerado: {ZIP_FILE}')

def main():
    with open(MKDOCS_FILE, 'r', encoding='utf-8') as f:
        try:
            config = yaml.safe_load(f)
        except yaml.constructor.ConstructorError:
            f.seek(0)
            config = yaml.unsafe_load(f)

    nav_section = config.get('nav', [])
    md_paths = parse_nav(nav_section)
    ensure_docs_exist(md_paths)
    criar_zip(md_paths)

if __name__ == '__main__':
    main()
