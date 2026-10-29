# Observador (sub-projeto 4c2, página 15): só a biblioteca padrão do Python, nenhuma dependência instalada.
# Construída pelo setup-agents-volumes.yml em /opt/observador-image.
FROM python:3.13-slim
COPY observador /app/observador
WORKDIR /app
ARG UID=1000
ARG GID=1000
RUN groupadd --gid ${GID} observador && useradd --uid ${UID} --gid ${GID} --no-create-home observador
USER observador
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/saude', timeout=3).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "observador"]
