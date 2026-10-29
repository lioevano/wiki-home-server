# Posto de agentes (sub-projeto 4c3, página 16): o servidor do Vibe Kanban (compilado do código-fonte pelo
# setup-posto-volumes.yml, imagem localhost/homeserver/vibe-kanban) com Node, git, gh e o Claude Code em cache.
ARG VIBE_KANBAN_IMAGE
FROM ${VIBE_KANBAN_IMAGE} AS vibe

FROM node:22-bookworm-slim
# git e ssh para os clones; gh para abrir PRs; tini como init (os agentes criam processos filhos).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git gnupg openssh-client tini \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*
COPY --from=vibe /usr/local/bin/server /usr/local/bin/vibe-kanban
# O usuário node da imagem (UID 1000) vira o dockeruser: os arquivos dos clones e dos dados ficam com ele.
ARG UID=1000
ARG GID=1000
RUN groupmod -o -g ${GID} node && usermod -o -u ${UID} -g ${GID} -d /home/posto -m -l posto node \
    && mkdir -p /repos /etc/claude-code /home/posto/.local/share \
    && chown posto:node /repos /home/posto/.local /home/posto/.local/share
USER posto
# O Vibe Kanban chama "npx -y @anthropic-ai/claude-code@<versão>": deixa essa versão no cache do npm.
ARG CLAUDE_CODE_VERSION
RUN npx -y @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} --version
# Só no 127.0.0.1: quem atende de fora é o Caddy (posto_porteiro), que divide a rede deste container.
ENV HOST=127.0.0.1 PORT=3000 HOME=/home/posto
WORKDIR /repos
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/vibe-kanban"]
