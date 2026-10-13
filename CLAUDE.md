@AGENTS.md

## Particularidades do Claude Code

- As skills de `.agents/skills/` são expostas ao Claude Code por invólucros em `.claude/skills/<nome>/SKILL.md` (mesmo `name`/`description`; o corpo manda seguir o arquivo canônico). Ao criar uma skill, crie os dois.
- Permissões do projeto: `.claude/settings.json`.
