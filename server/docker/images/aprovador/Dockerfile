# Aprovador (sub-projeto 4c3, página 16): só a biblioteca padrão do Python, nenhuma dependência instalada.
# Construída pelo setup-agents-volumes.yml em /opt/aprovador-image.
FROM python:3.13-slim
COPY aprovador /app/aprovador
WORKDIR /app
ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} aprovador && useradd --uid ${UID} --gid ${GID} --no-create-home aprovador
USER aprovador
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/saude', timeout=3).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "aprovador"]
