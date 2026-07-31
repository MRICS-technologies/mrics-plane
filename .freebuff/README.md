# Freebuff project guidance

## Understanding Anything bridge

Freebuff has no verified native skill auto-discovery mechanism. This directory therefore provides an explicit, versioned bridge rather than claiming a plugin installation.

Before a **discovery, onboarding, explanation, or documentation-planning** task, give Freebuff this first instruction:

> Read `.freebuff/understanding-anything/SKILL.md`, classify the reader's current understanding, then read only the relevant files in `.freebuff/understanding-anything/references/`. Use the method to build an evidence-based understanding report. Do not edit files until a separate implementation brief is provided.

Use `.freebuff/prompts/understanding-anything-discovery.md` as the reusable task template.

### Guardrails

- This bridge is for understanding and planning, not autonomous architecture or code changes.
- Ground claims in repository code, tests, and committed documentation; label uncertainty.
- Treat the skill as an explicit prompt dependency. It is not automatically loaded by the Freebuff CLI.
- Keep secrets, tokens, connection strings, and real webhook payloads out of prompts, reports, and Git.
- Freebuff is a bounded junior worker. Dahab/Hermes reviews all reports and independently verifies any resulting implementation work.
