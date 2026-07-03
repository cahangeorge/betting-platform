# Bet Agent Setup

Project-specific agent configuration lives in `.codex/agents/`.

This workspace keeps plugins, hooks, and shared skill packs global in `~/.codex` instead of vendoring them into the repo. Use the global tooling for shared capabilities:

- Context7
- Playwright MCP
- Chrome DevTools MCP
- Serena
- Repomix
- oh-my-codex (OMX) workflow plugin

Nested projects/submodules (`OddsHarvester/`, `penaltyblog/`, `soccerdata/`) may have their own instructions. Read those before changing them.
