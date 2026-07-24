# Codex Model Routing Policy

This project uses a tiered model strategy: Codex Spark for pure lookup, Luna for lightweight agentic support, Terra for normal delivery, and Sol only for high-risk reasoning or final verification.

## Default session model

Repo-local `.codex/config.toml` defaults to:

```toml
model = "gpt-5.6-terra"
model_reasoning_effort = "medium"
```

This is the day-to-day cost/performance lane for normal implementation.

## Agent lanes

| Lane | Agent(s) | Model | Effort | Use when | Cost rule |
|---|---|---:|---:|---|---|
| Explore | `*-explorer` | `gpt-5.3-codex-spark` | low | read-only repo lookup, file mapping, command discovery | cheapest/fastest; never implement |
| Light agentic | global `analyst`/`writer`/`vision` or explicit `--model` | `gpt-5.6-luna` | low/medium | lightweight analysis, docs, screenshots, bounded synthesis | use when Spark is too narrow but Terra is unnecessary |
| Implement | `*-executor` | `gpt-5.6-terra` | medium | scoped code/docs/config changes | default worker lane |
| Verify | `*-qa-verifier` | `gpt-5.6-sol` | high | final evidence, browser runtime, cross-boundary validation | use once near the gate, not continuously |
| Risk review | `bet-scrape-reviewer` | `gpt-5.6-sol` | high | scraper/prediction/odds risk review | only for brittle/high-impact surfaces |

## Escalation rules

Start cheap and escalate only when useful:

1. Use explorer for facts and file paths.
2. Use executor for a bounded patch.
3. Use verifier after the patch or when correctness is uncertain.
4. Use frontier/high reasoning earlier only for security, migrations, money/billing, auth, production data, scraper brittleness, or repeated failures.

## Token discipline

- Do not load all skills or agent docs just in case.
- Activate 1 workflow skill plus 1-3 supporting skills maximum.
- Prefer targeted `rg`, focused file ranges, and exact commands over broad scans.
- Keep subagent tasks bounded and non-overlapping.
- Report verification evidence, not full logs, unless failure details matter.

## OMX usage

OMX remains optional. Use normal Codex for small tasks. Use OMX for complex planning/orchestration:

```text
$deep-interview -> $ralplan -> $ultragoal
```

Use `$team` only when work can be split into independent write scopes. Use `--worktree=<task>` for risky or parallel sessions. Do not use `--madmax` unless explicitly requested.
