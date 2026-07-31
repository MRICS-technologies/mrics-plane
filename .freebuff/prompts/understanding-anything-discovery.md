# Understanding discovery brief

Read `.freebuff/understanding-anything/SKILL.md`. Classify the audience's current understanding, then load only the relevant reference files under `.freebuff/understanding-anything/references/`.

## Task
Understand the specified system from first principles before proposing any changes.

## Evidence rules

- Read the relevant repository code, tests, and current documentation.
- Distinguish verified facts from assumptions and unknowns.
- Do not edit files, install dependencies, change configuration, commit, push, deploy, or expose secrets.

## Required report

1. **First-principles model:** problem, essential components, causal relationships, and system boundaries.
2. **Reader model:** what the named audience must understand and likely misconceptions.
3. **Evidence and uncertainty:** source paths for claims plus open questions.
4. **Validation questions:** what the audience should be able to explain, predict, or falsify after the documentation/onboarding.
5. **Minimal next step:** a bounded proposal only; do not implement it.
