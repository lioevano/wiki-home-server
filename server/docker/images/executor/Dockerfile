# Executor do sysadmin (sub-projeto 5a, página 19): FastMCP + ansible-core, como o ops, mais o aprovador (pedidos
# e Telegram). O contexto de build traz requirements.txt, requirements.yml e as pastas ops, aprovador e executor.
# Não desliga a checagem de chave dos hosts: o known_hosts é assunto do deploy.
FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY requirements.yml /tmp/requirements.yml
RUN ansible-galaxy collection install -r /tmp/requirements.yml -p /usr/share/ansible/collections
COPY ops /app/ops
COPY aprovador /app/aprovador
COPY executor /app/executor
WORKDIR /app
ENV ANSIBLE_VAULT_PASSWORD_FILE=/segredos/vault_senha
# O compose roda com o UID/GID do dockeruser: o ssh do Ansible aborta se o UID não existir no /etc/passwd.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} executor && useradd --uid ${UID} --gid ${GID} --create-home executor
USER executor
ENTRYPOINT ["python", "-m", "executor"]
