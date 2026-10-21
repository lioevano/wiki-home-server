# Design: política de versões das imagens

- **Data:** 2026-10-21
- **Autor:** Léo Ivan (com Claude)
- **Status:** decidido de forma autônoma, a pedido do Léo ("pode seguir da mesma forma autônoma com os demais pontos").
- **Caminho:** bounded+. Muda a tag de 16 serviços e a configuração do Diun, sem mudar a arquitetura.
- **Origem:** sugestão da rodada de pendências menores. O `server/AGENTS.md` pede "imagens com versão fixada sempre que possível", mas 16 serviços ainda usam `:latest`.

## 1. Problema

Com `:latest`, um `Update the stack` com **Re-pull** ou uma reconstrução traz a versão do dia, que pode quebrar sem aviso (mudança de configuração, de API ou de banco). E o repositório deixa de dizer o que roda de fato.

O Diun, do jeito que está, só avisa quando o **digest da mesma tag** muda. Isso só serve para `:latest`: fixar as versões sem mexer nele faria o Diun parar de avisar.

## 2. Decisões

| # | Tema | Escolha |
|---|---|---|
| V1 | Tags | Toda imagem de compose tem versão. Imagens locais (`localhost/homeserver/*`) e as que vêm de variável (`${…}`) ficam de fora da regra. Para as imagens da linuxserver.io, a tag é a versão do aplicativo (`4.0.20`), sem o sufixo `-lsNNN`. Assim o Diun avisa quando sai versão nova do aplicativo, não a cada rebuild da imagem. O Jellyfin fica na série (`12.2`), porque o projeto só publica a série e builds datados. |
| V2 | Versões escolhidas (2026-10-21, as mais recentes estáveis) | Prometheus `v3.15.0`, Loki `3.7.9`, blackbox-exporter `v0.29.0`, docker-socket-proxy `v0.5.0` (o mesmo digest do `latest` de hoje), Homepage `v2.6.0`, Jellyfin `12.2`, Seerr `v3.5.0`, Sonarr `4.0.20`, Radarr `6.4.4`, Lidarr `3.1.0`, Prowlarr `2.6.5`, Bazarr `1.6.2`, FlareSolverr `v3.5.2`, gluetun `v3.41.3`, qBittorrent `5.3.0`. |
| V3 | Diun | Os dois Diuns (`diun`, `diun_ai`) passam a observar o **repositório** de cada imagem, com `DIUN_DEFAULTS_WATCHREPO=true`, `DIUN_DEFAULTS_SORTTAGS=semver`, `DIUN_DEFAULTS_MAXTAGS=10` e `DIUN_DEFAULTS_INCLUDETAGS=^v?\d+(\.\d+)+$`. Um aviso = uma tag de versão nova publicada. Tags como `16-alpine` (Postgres), `latest` e `develop` não entram. |
| V4 | Atualizar | Continua manual, uma aplicação por vez: notas da versão → trocar a tag na wiki (bloco literal ou compose) → `sync` → `Update the stack` com **Re-pull**. A página 03/09 (atualização segura) ganha esse fluxo. |
| V5 | Pinos antigos | Traefik `v2.11.2`, cloudflared `2024.5.0`, Authelia `4.38.0`, Portainer `2.19.4` e os Postgres **não** mudam aqui. Subir Traefik para a v3, Authelia para a 4.39 ou o Postgres de versão principal pede migração própria. O Diun passa a avisar quando há versão nova. |
| V6 | Guarda | O teste `test_imagens_com_versao` falha se um compose usar `:latest` ou imagem sem tag. |
