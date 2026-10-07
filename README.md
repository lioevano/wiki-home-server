# Servidor doméstico do Léo Ivan

Wiki e implementação de um servidor doméstico com Proxmox VE, ZFS/NFS, Ansible, Docker/Portainer,
Traefik, Cloudflare Tunnel e Authelia. A wiki (`wiki/`) é a fonte da verdade; o `server/`
contém a implementação e é verificado contra ela pelo `tools/wikisync`.

- Site: https://lioevano.github.io/wiki-home-server/
- Comece por [`CLAUDE.md`](CLAUDE.md) (fluxo de trabalho) e [`INDEX.md`](INDEX.md) (mapa do repositório).

```bash
python tools/dev.py setup   # cria o ambiente e instala dependências
python tools/dev.py serve   # wiki local em http://127.0.0.1:8000
python tools/dev.py check   # divergências entre wiki e server
```
