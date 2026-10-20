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
RUN useradd --uid 1000 --create-home ops
USER ops
ENTRYPOINT ["python", "-m", "ops.server"]
