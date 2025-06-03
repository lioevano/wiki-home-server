import os
import zipfile

# Nome do arquivo zip final
zip_filename = "homelab-wiki-inicial.zip"

# Estrutura do repositório
files = [
    "homelab-wiki/docs/index.md",
    "homelab-wiki/docs/01-manual-implementacao/index.md",
    "homelab-wiki/docs/01-manual-implementacao/00-preparacao-planejamento.md",
    "homelab-wiki/docs/01-manual-implementacao/01-maquina-controle-ansible.md",
    "homelab-wiki/docs/01-manual-implementacao/02-proxmox-ve-host.md",
    "homelab-wiki/docs/01-manual-implementacao/03-provisionamento-vms.md",
    "homelab-wiki/docs/01-manual-implementacao/04-configuracao-base-vms-ubuntu.md",
    "homelab-wiki/docs/01-manual-implementacao/05-rede-segura.md",
    "homelab-wiki/docs/01-manual-implementacao/06-deploy-portainer-geral.md",
    "homelab-wiki/docs/01-manual-implementacao/07-stack-ia-rag.md",
    "homelab-wiki/docs/01-manual-implementacao/08-stack-midia.md",
    "homelab-wiki/docs/01-manual-implementacao/09-stack-produtividade-automacao.md",
    "homelab-wiki/docs/01-manual-implementacao/10-stack-monitoramento.md",
    "homelab-wiki/docs/02-visao-geral-arquitetura/index.md",
    "homelab-wiki/docs/02-visao-geral-arquitetura/01-fluxo-rede-acesso-externo.md",
    "homelab-wiki/docs/02-visao-geral-arquitetura/02-virtualizacao-proxmox.md",
    "homelab-wiki/docs/02-visao-geral-arquitetura/03-armazenamento-zfs-nfs.md",
    "homelab-wiki/docs/02-visao-geral-arquitetura/04-automacao-ansible.md",
    "homelab-wiki/docs/02-visao-geral-arquitetura/05-gerenciamento-containers.md",
    "homelab-wiki/docs/02-visao-geral-arquitetura/06-principios-seguranca.md",
    "homelab-wiki/docs/03-guias-sustentacao/index.md",
    "homelab-wiki/docs/03-guias-sustentacao/01-adicionando-novo-servico-docker.md",
    "homelab-wiki/docs/03-guias-sustentacao/02-modificando-configuracoes-existentes.md",
    "homelab-wiki/docs/03-guias-sustentacao/03-troubleshooting-comum.md",
    "homelab-wiki/docs/03-guias-sustentacao/04-gerenciando-redes-docker.md",
    "homelab-wiki/docs/03-guias-sustentacao/05-passthrough-hardware-adicional.md",
    "homelab-wiki/docs/04-manutencao-recuperacao/index.md",
    "homelab-wiki/docs/04-manutencao-recuperacao/01-rotinas-manutencao.md",
    "homelab-wiki/docs/04-manutencao-recuperacao/02-backup-restore-estrategia.md",
    "homelab-wiki/docs/04-manutencao-recuperacao/03-cicd-basico-ansible.md",
    "homelab-wiki/docs/04-manutencao-recuperacao/04-reconstruindo-infraestrutura.md",
    "homelab-wiki/docs/04-manutencao-recuperacao/05-migrando-hardware-rede.md",
    "homelab-wiki/docs/assets/images/.keep",  # marcador de pasta
    "homelab-wiki/mkdocs.yml"
]

# Criar o ZIP
with zipfile.ZipFile(zip_filename, 'w') as zipf:
    for filepath in files:
        zipf.writestr(filepath, "")  # arquivos vazios

print(f"Arquivo '{zip_filename}' criado com sucesso!")
