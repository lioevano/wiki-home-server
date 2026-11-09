# Sysadmin (página 19): a imagem oficial do Hermes Agent mais o que o sysadmin usa no trabalho: Ansible, gh, git,
# ssh, o ambiente do `tools/dev.py` (check, test, lint, build) e o cliente do Honcho (honcho-ai) para o plugin.
#
# Contexto de build (montado pelo setup-sysadmin.yml), com estes caminhos relativos à raiz do contexto:
#   requirements-dev.txt       cópia do requirements-dev.txt da raiz do repositório
#   wiki/requirements.txt      cópia do wiki/requirements.txt (o primeiro faz `-r wiki/requirements.txt`)
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
# (HOMESERVER_VENV=/opt/dev). O uv é o do pm, o mesmo que montou o /opt/hermes/.venv.
COPY requirements-dev.txt /tmp/dev/requirements-dev.txt
COPY wiki/requirements.txt /tmp/dev/wiki/requirements.txt
RUN set -eu; \
    uv="$(cd /opt/hermes && python3 -c 'from pm import installed_package; print(installed_package("uv").binary)')"; \
    "$uv" pip install --no-cache --python /opt/hermes/.venv/bin/python "honcho-ai==${HONCHO_AI_VERSION}"; \
    /opt/hermes/.venv/bin/python -c "import honcho"; \
    "$uv" venv --python /usr/local/bin/python3 /opt/ansible; \
    "$uv" pip install --no-cache --python /opt/ansible/bin/python "ansible-core==${ANSIBLE_CORE_VERSION}"; \
    for c in ansible ansible-playbook ansible-galaxy ansible-vault ansible-inventory ansible-config; do \
        ln -s "/opt/ansible/bin/$c" "/usr/local/bin/$c"; \
    done; \
    ansible --version; \
    "$uv" venv --seed --python /usr/local/bin/python3 /opt/dev; \
    "$uv" pip install --no-cache --python /opt/dev/bin/python -r /tmp/dev/requirements-dev.txt; \
    rm -rf /tmp/dev
ENV HOMESERVER_VENV=/opt/dev

# Mantém o ENTRYPOINT e o CMD da imagem do Hermes (despachante do s6).
