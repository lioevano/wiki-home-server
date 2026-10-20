"""MCP de operações do homeserver (base dos agentes, página 13 da wiki).

Containers e stacks pela API do Portainer; playbooks Ansible pelo runner embutido (só no modo controle).
A lógica fica em módulos sem dependências externas; server.py só registra as ferramentas no FastMCP.
"""
