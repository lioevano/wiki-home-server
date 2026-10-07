from pathlib import Path
import re

ROOT = Path('/home/user/docs/wiki-extracted/wiki-home-server')


def replace_text(path_str, replacements):
    path = ROOT / path_str
    text = path.read_text(encoding='utf-8')
    original = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding='utf-8')
        print(f'updated: {path_str}')
    else:
        print(f'unchanged: {path_str}')


def regex_replace(path_str, patterns):
    path = ROOT / path_str
    text = path.read_text(encoding='utf-8')
    original = text
    for pattern, repl in patterns:
        text = re.sub(pattern, repl, text, flags=re.MULTILINE)
    if text != original:
        path.write_text(text, encoding='utf-8')
        print(f'updated(regex): {path_str}')
    else:
        print(f'unchanged(regex): {path_str}')


# 1) mkdocs.yml: fix appendices nav placement and version block
mkdocs_path = ROOT / 'mkdocs.yml'
mkdocs = mkdocs_path.read_text(encoding='utf-8')
appendix_nav = """  - '📖 Apêndices':
    - 'Matriz de Compatibilidade ROCm/GPU': '99-apendices/matriz-compatibilidade-rocm-gpu.md'
    - 'Estimativa de Custos GCP e SLA': '99-apendices/estimativa-custos-gcp.md'
    - 'Glossário de Variáveis Ansible': '99-apendices/glossario-variaveis-ansible.md'
"""
if appendix_nav not in mkdocs:
    marker = "  - '🔄 Soluções Alternativas':\n    - 'Visão Geral': '06-solucoes-alternativas/index.md'\n    - 'Hypervisors': '06-solucoes-alternativas/01-hypervisors.md'\n    - 'Automação de Configurações': '06-solucoes-alternativas/02-automacao-config.md'\n    - 'Gerenciamento de Containers': '06-solucoes-alternativas/03-gerenciamento-containers.md'\n    - 'Proxy Reverso': '06-solucoes-alternativas/04-proxy-reverso.md'\n    - 'Acesso Externo': '06-solucoes-alternativas/05-acesso-externo.md'\n    - 'Autenticação SSO': '06-solucoes-alternativas/06-autenticacao-sso.md'\n    - 'Servidores de Mídia': '06-solucoes-alternativas/07-servidores-midia.md'\n    - 'Sincronização de Arquivos': '06-solucoes-alternativas/08-sincronizacao-arquivos.md'\n    - 'Monitoramento e Logs': '06-solucoes-alternativas/09-monitoramento-logs.md'\n    - 'Plataformas de Automação': '06-solucoes-alternativas/10-plataformas-automacao.md'\n"
    mkdocs = mkdocs.replace(marker, marker + appendix_nav)
mkdocs = mkdocs.replace(
    "  version:\n    provider: mike # Para versionamento de documentação com mike, se necessário  - '📖 Apêndices':\n    - 'Matriz de Compatibilidade ROCm/GPU': '99-apendices/matriz-compatibilidade-rocm-gpu.md'\n    - 'Estimativa de Custos GCP e SLA': '99-apendices/estimativa-custos-gcp.md'\n    - 'Glossário de Variáveis Ansible': '99-apendices/glossario-variaveis-ansible.md'\n",
    "  version:\n    provider: mike # Para versionamento de documentação com mike, se necessário\n",
)
mkdocs_path.write_text(mkdocs, encoding='utf-8')
print('updated: mkdocs.yml')

# 2) Broken relative links and step ordering
replace_text('docs/01-manual-implementacao/00-preparacao-planejamento.md', [
    ('../../05-guia-estudos/03-aprofundamento-ansible.md', '../05-guia-estudos/03-aprofundamento-ansible.md'),
    ('../../05-guia-estudos/04-aprofundamento-docker-networking.md', '../05-guia-estudos/04-aprofundamento-docker-networking.md'),
    ('../../05-guia-estudos/01-aprofundamento-proxmox-ve.md', '../05-guia-estudos/01-aprofundamento-proxmox-ve.md'),
    ('../../05-guia-estudos/05-aprofundamento-traefik-authelia.md', '../05-guia-estudos/05-aprofundamento-traefik-authelia.md'),
    ('../../05-guia-estudos/02-aprofundamento-zfs.md', '../05-guia-estudos/02-aprofundamento-zfs.md'),
])

replace_text('docs/01-manual-implementacao/02-proxmox-ve-host.md', [
    ('../../03-guias-sustentacao/12-guia-snapshots-zfs.md', '../03-guias-sustentacao/12-guia-snapshots-zfs.md'),
])

replace_text('docs/04-manutencao-recuperacao/01-rotinas-manutencao.md', [
    ('(10-atualizacao-segura-componentes-criticos.md)', '(../03-guias-sustentacao/10-atualizacao-segura-componentes-criticos.md)'),
    ('(03-troubleshooting-comum.md#ferramentas-essenciais-de-diagnóstico)', '(../03-guias-sustentacao/03-troubleshooting-comum.md#ferramentas-essenciais-de-diagnóstico)'),
])

replace_text('docs/04-manutencao-recuperacao/02-backup-restore-estrategia.md', [
    ('[Seção 11.1 do documento original](../TODO-link-secao-11.1-original.md)', 'subseção desta própria página sobre backup lógico do PostgreSQL'),
    ('(12-guia-snapshots-zfs.md)', '(../03-guias-sustentacao/12-guia-snapshots-zfs.md)'),
])

replace_text('docs/05-guia-estudos/06-seguranca-avancada-homelab.md', [
    ('[Rotinas de Manutenção](01-rotinas-manutencao.md)', '[Rotinas de Manutenção](../04-manutencao-recuperacao/01-rotinas-manutencao.md)'),
])

# 3) Standardize Ansible paths in docs
common_path_replacements = [
    ('ansible/vault.yml', 'ansible/inventories/home/group_vars/all/vault.yml'),
    ('ansible/vars/main.yml', 'ansible/inventories/home/group_vars/all/main.yml'),
]
for file_rel in [
    'docs/03-guias-sustentacao/13-usando-geminicli.md',
    'docs/01-manual-implementacao/11-stack-automacao-n8n.md',
    'docs/04-manutencao-recuperacao/05-migrando-hardware-rede.md',
    'docs/03-guias-sustentacao/02-modificando-configuracoes-existentes.md',
]:
    replace_text(file_rel, common_path_replacements)

# 4) Improve implementation index ordering and include n8n step explicitly
regex_replace('docs/01-manual-implementacao/index.md', [
    (r'11\. \*\*\[Stack de Monitoramento \(Glances, Prometheus, Grafana, Loki\)\]\(10-stack-monitoramento\.md\):\*\*\n\s+Configurando ferramentas para monitorar a saúde e performance do seu servidor\.',
     "11. **[Stack de Monitoramento (Glances, Prometheus, Grafana, Loki)](10-stack-monitoramento.md):**\n    Configurando ferramentas para monitorar a saúde, os logs e a performance do seu servidor.\n12. **[Stack de Automação Low-Code (n8n)](11-stack-automacao-n8n.md):**\n    Implantando workflows low-code para integrações, alertas e automações avançadas."),
])

# 5) Fix n8n page: paths, vars_files, env conventions and final link
replace_text('docs/01-manual-implementacao/11-stack-automacao-n8n.md', [
    ('        - ../vars/main.yml\n        - ../vault.yml', '        - ../inventories/home/group_vars/all/main.yml\n        - ../inventories/home/group_vars/all/vault.yml'),
    ('            src: ../templates/portainer_stack_env.j2', '            src: ../templates/portainer_stack_env.j2'),
    ('                stack_name: "n8n"\n                stack_configs:\n                  - { name: \'N8N_CONFIG_PATH\', value: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/n8n/config" }', '                stack_name: "automation-n8n"\n                stack_configs:\n                  - { name: \'N8N_CONFIG_PATH\', value: "{{ vm_nfs_mount_base_path }}/{{ zfs_docker_volumes_dataset_name }}/n8n/config" }\n                  - { name: \'N8N_SUBDOMAIN\', value: "{{ n8n_subdomain }}" }'),
    ('### Docker Compose para n8n (`docker/stacks/automation/n8n-compose.yml`)', '### Docker Compose para n8n (`docker/stacks/automation/n8n/docker-compose.yml`)'),
    ('# docker/stacks/automation/n8n-compose.yml', '# docker/stacks/automation/n8n/docker-compose.yml'),
    ('      - N8N_HOST={{ n8n_subdomain }}.{{ base_domain }}', '      - N8N_HOST=${N8N_SUBDOMAIN}.${BASE_DOMAIN}'),
    ('      - WEBHOOK_URL=https://{{ n8n_subdomain }}.{{ base_domain }}/', '      - WEBHOOK_URL=https://${N8N_SUBDOMAIN}.${BASE_DOMAIN}/'),
    ('      traefik.http.routers.n8n.rule: "Host(`{{ n8n_subdomain }}.{{ base_domain }}`)"', '      traefik.http.routers.n8n.rule: "Host(`${N8N_SUBDOMAIN}.${BASE_DOMAIN}`)"'),
    ('    # ansible/inventories/home/group_vars/all/main.yml\n    # ...\n    n8n_subdomain: "n8n"', '    # ansible/inventories/home/group_vars/all/main.yml\n    # ...\n    n8n_subdomain: "n8n"'),
    ('https://n8n.seudominio.com', 'https://n8n.${BASE_DOMAIN} (ou o domínio real equivalente)'),
    ('[nova seção no Guia de Estudos](/?path=docs/05-guia-estudos/09-aprofundamento-n8n.md)', '[nova seção no Guia de Estudos](../05-guia-estudos/09-aprofundamento-n8n.md)'),
])

# 6) Improve GeminiCLI page to use real path and clearer install role
replace_text('docs/03-guias-sustentacao/13-usando-geminicli.md', [
    ('Crie a estrutura do role:** `ansible/roles/tools/ai-cli-tools`', 'Crie a estrutura do role:** `ansible/roles/tools/ai-cli-tools/`'),
    ('Primeiro, obtenha uma chave de API para o Gemini no [Google AI Studio](https://aistudio.google.com/app/apikey). Em seguida, adicione-a ao seu `ansible/inventories/home/group_vars/all/vault.yml` (a mesma que usamos para o LiteLLM).', 'Primeiro, obtenha uma chave de API para o Gemini no [Google AI Studio](https://aistudio.google.com/app/apikey). Em seguida, adicione-a ao seu `ansible/inventories/home/group_vars/all/vault.yml`.'),
])

# 7) Fix a few path references in maintenance/migration docs
replace_text('docs/03-guias-sustentacao/09-integrando-novos-servicos-stacks-existentes.md', [
    ('Consulte o [Guia de Snapshots ZFS](12-guia-snapshots-zfs.md) para mais detalhes.', 'Consulte o [Guia de Snapshots ZFS](12-guia-snapshots-zfs.md) para mais detalhes.'),
])

# 8) Root index: implementation steps count mention n8n explicitly if absent
index_path = ROOT / 'docs/index.md'
index_text = index_path.read_text(encoding='utf-8')
if 'Stack de Automação Low-Code (n8n)' not in index_text and '01-manual-implementacao/index.md' in index_text:
    insert_marker = '1. [Implementação](01-manual-implementacao/index.md)\n'
    index_text = index_text.replace(insert_marker, insert_marker + '   - Inclui a sequência revisada de infraestrutura base, stacks principais, monitoramento e automação low-code com n8n.\n')
    index_path.write_text(index_text, encoding='utf-8')
    print('updated: docs/index.md')
else:
    print('unchanged: docs/index.md')
