# MCP ops (página 13): FastMCP + ansible-core. Construída pelo setup-agents-volumes.yml em /opt/ops-image,
# junto com o requirements.txt (versões do group_vars) e o requirements.yml das coleções do repositório.
FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY requirements.yml /tmp/requirements.yml
RUN ansible-galaxy collection install -r /tmp/requirements.yml -p /usr/share/ansible/collections
COPY ops /app/ops
WORKDIR /app
# O compose roda com o UID/GID do dockeruser: o ssh do Ansible aborta se o UID não existir no /etc/passwd.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} ops && useradd --uid ${UID} --gid ${GID} --create-home ops
USER ops
ENTRYPOINT ["python", "-m", "ops.server"]
