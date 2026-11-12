# Sysadmin (página 02): a imagem oficial do Hermes Agent mais o que o sysadmin usa no trabalho: Ansible, gh, git,
# ssh, o ambiente do `tools/dev.py` (check, test, lint, build), as coleções do Ansible e o cliente do Honcho
# (honcho-ai) para o plugin.
#
# Contexto de build (montado pelo setup-sysadmin.yml), com estes caminhos relativos à raiz do contexto:
#   requirements-dev.txt       cópia do requirements-dev.txt da raiz do repositório
#   wiki/requirements.txt      cópia do wiki/requirements.txt (o primeiro faz `-r wiki/requirements.txt`)
#   requirements.yml           cópia do server/ansible/requirements.yml (coleções do Ansible)
# Argumentos de build (versões vindas do group_vars): HERMES_VERSION, ANSIBLE_CORE_VERSION, HONCHO_AI_VERSION.
#
# A imagem do Hermes roda o s6-overlay como root e ele troca para o usuário de HERMES_UID: por isso esta imagem
# não define USER. O Python do Hermes é o /opt/hermes/.venv (selado, criado com uv, sem pip): os pacotes entram
# nele pelo uv que a própria imagem traz (pm), como root e só na construção, nunca em tempo de execução.
ARG HERMES_VERSION
FROM nousresearch/hermes-agent:${HERMES_VERSION}
ARG ANSIBLE_CORE_VERSION
ARG HONCHO_AI_VERSION

USER root

# gh do repositório oficial (cli.github.com), com a chave num keyring e `signed-by`; git e ssh já vêm na base,
# mas ficam declarados.
RUN apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends ca-certificates curl git openssh-client \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL --retry 3 -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
        https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# honcho-ai no Python do Hermes (o plugin do Honcho importa o SDK); ansible-core num ambiente à parte em /opt/ansible,
# para não mexer nas dependências do Hermes, com os comandos no PATH; e o ambiente do dev.py em /opt/dev
# (HOMESERVER_VENV=/opt/dev). O uv é o do pm, o mesmo que montou o /opt/hermes/.venv, lido pelo uv_launcher: o
# installed_package recusa o uv ("internal PM tooling", Hermes v0.22.5) e o build para se ele não vier. As coleções do Ansible
# entram na construção, em /usr/share/ansible/collections (caminho padrão dos dois ansible-core da imagem): o
# `dev.py lint` e o syntax-check as acham sem baixar nada na partida.
COPY requirements-dev.txt /tmp/dev/requirements-dev.txt
COPY wiki/requirements.txt /tmp/dev/wiki/requirements.txt
COPY requirements.yml /tmp/dev/requirements.yml
RUN set -eu; \
    uv="$(cd /opt/hermes && python3 -c 'from pm import uv_launcher; print(uv_launcher("uv") or "")')"; \
    test -x "$uv"; \
    "$uv" pip install --no-cache --python /opt/hermes/.venv/bin/python "honcho-ai==${HONCHO_AI_VERSION}"; \
    /opt/hermes/.venv/bin/python -c "import honcho"; \
    "$uv" venv --python /usr/local/bin/python3 /opt/ansible; \
    "$uv" pip install --no-cache --python /opt/ansible/bin/python "ansible-core==${ANSIBLE_CORE_VERSION}"; \
    for c in ansible ansible-playbook ansible-galaxy ansible-vault ansible-inventory ansible-config; do \
        ln -s "/opt/ansible/bin/$c" "/usr/local/bin/$c"; \
    done; \
    ansible --version; \
    ansible-galaxy collection install -r /tmp/dev/requirements.yml -p /usr/share/ansible/collections; \
    "$uv" venv --seed --python /usr/local/bin/python3 /opt/dev; \
    "$uv" pip install --no-cache --python /opt/dev/bin/python -r /tmp/dev/requirements-dev.txt; \
    rm -rf /tmp/dev
ENV HOMESERVER_VENV=/opt/dev

# gh e git push com a conta de máquina: o Hermes tira GH_TOKEN e GITHUB_TOKEN de todo comando do agente, então o
# token chega como SYSADMIN_GITHUB_TOKEN e o /usr/local/bin/gh (à frente do /usr/bin/gh no PATH) o traduz. O git
# autentica no GitHub por esse gh e assina os commits como a conta de máquina.
COPY gh /usr/local/bin/gh
RUN chmod 755 /usr/local/bin/gh \
    && git config --system credential.https://github.com.helper '' \
    && git config --system --add credential.https://github.com.helper '!/usr/local/bin/gh auth git-credential' \
    && git config --system user.name lioevano-sysadmin \
    && git config --system user.email lioevano-sysadmin@users.noreply.github.com

# Mantém o ENTRYPOINT e o CMD da imagem do Hermes (despachante do s6).
