# AGENTS.md

Codex operating guidelines for this repository. These rules are intended to reduce common LLM coding mistakes while keeping execution practical, and are written to be reusable across projects.

Use judgment for trivial tasks. These guidelines bias toward correctness, clarity, and minimal diffs over speed.

## 1. Think Before Coding

Do not silently guess.

- State assumptions when they materially affect the implementation.
- If the request is ambiguous and there are multiple reasonable interpretations, surface them instead of picking one silently.
- If a simpler or safer path exists, say so before implementing.
- If you are blocked by missing requirements, ask a short clarifying question instead of inventing behavior.

## 2. Prefer Simple Solutions

Implement the smallest change that fully solves the requested problem.

- Avoid over-engineering. Only make changes that are directly requested or clearly necessary; keep solutions simple and focused.
- Do not add features, options, abstractions, or configurability that were not requested.
- Do not generalize for hypothetical future use.
- Avoid introducing new layers, helpers, or patterns for one-off logic.
- Do not add error handling, fallbacks, validation, feature flags, or backwards-compatibility shims for scenarios that cannot happen. Trust internal code and framework guarantees; validate at system boundaries such as user input and external APIs.
- If the same result can be achieved with materially less code, prefer the shorter version.

## 3. Make Surgical Changes

Keep diffs tightly scoped to the task.

- Touch only files and lines that are needed for the requested outcome.
- Do not refactor adjacent code unless the task requires it.
- Do not add docstrings, comments, type annotations, or other cleanup to code you did not otherwise need to change. Add comments only where the logic is not self-evident.
- Match the surrounding style and conventions of the repository.
- Do not remove unrelated dead code, comments, or formatting noise just because you noticed it.
- Clean up only issues directly created by your own change, such as unused imports you introduced.
- When the requested change removes code and you are certain something is unused, delete it cleanly instead of leaving compatibility hacks such as unused renamed variables, re-exports, or "removed" comments.

## 4. Work Backward From Verification

Define success in a way that can be checked.

- For bug fixes, prefer reproducing the issue first, then fixing it.
- For new behavior, prefer adding or updating tests when the repo already uses tests.
- For refactors, preserve behavior and verify before and after when practical.
- End work by running the smallest meaningful verification available, such as targeted tests, lint, build, or a focused manual check.
- If verification fails because of your change, keep fixing or clearly state the blocker.
- If verification fails for an unrelated pre-existing reason, record the command, evidence, and residual risk instead of silently fixing unrelated code.

For multi-step tasks, think in this format:

1. Change
2. Verify
3. Repeat until the requested outcome is satisfied

## 5. Communication

Keep communication concise and useful.

- Share short progress updates during longer tasks.
- Mention important assumptions, tradeoffs, and risks.
- If you notice unrelated problems, mention them briefly instead of fixing them without permission.

## 6. Safety Rails

- Never overwrite or revert user changes unless explicitly asked.
- Do not make destructive changes outside the requested scope.
- When working in an existing codebase, preserve established patterns unless the user asks for a redesign.
- Never print, copy, or modify secrets from `.env`; use `.env.example` for documentation or configuration references. If the user explicitly asks you to write local config, do not echo secret values back in the response.
- Do not reformat whole files or projects unless requested or required by the touched toolchain.
- Do not reorder unrelated imports, update lockfiles, or clean unrelated dead code unless the task requires it.

## 7. Git And Multi-Agent Hygiene

- After completing a coherent change, prefer committing promptly when the user has asked for implementation or commit-ready work. Stage and commit only your own changes; do not include unrelated user edits or changes made by other agents.
- Assume other agents may be working in the same repository at the same time. Before editing, staging, or committing, check the current worktree state, keep your diff scoped, avoid overlapping ownership when possible, and never overwrite or revert changes you did not make.

## 8. Documentation-First Workflow

Use docs according to task risk and scope.

Fast path is for small localized work, such as wording fixes, link fixes, code explanations, command inspection, narrow test repairs, and single-file bug fixes that do not change public APIs, durable semantics, or long-lived project rules.

Fast path:

- Read only the directly relevant docs when needed.
- Do not create a plan just to satisfy process.
- Make the smallest viable change and run the smallest meaningful verification, or explain why verification was not run.

Plan path is for higher-risk work: runtime behavior, public APIs, UI interaction, data flow, configuration semantics, architecture boundaries, research methodology, domain baselines, multi-file logic, or anything needing a reusable verification or rollback trail.

Plan path:

- Start from the project's docs index when one exists, then read only directly relevant overview, reference, guide, and plan documents.
- Reuse an existing active plan, roadmap, backlog, or reference page when it fits; create a new short kebab-case plan only when durable tracking is needed and no existing doc fits.
- Record the minimum useful plan: goal, scope, constraints, docs checked, execution steps, verification plan, progress, changed files, and verification results.
- Implement the smallest viable change against the plan, and update the plan first if scope or design changes.
- If docs conflict with code or with each other, pause and surface the conflict.

Document lifecycle:

- Keep planning docs active and finite. After a plan-path task is completed, update its status and either keep it only if it still guides active work, archive it, or move durable conclusions into stable overview, reference, or guide docs.
- Avoid creating new docs when an existing active plan, backlog, or reference page can be updated cleanly.

Completion for plan-path work requires checked docs, an updated plan, recorded verification, and a final response that names the docs checked, the plan updated, and the verification run. If unsure what to run, use the project's verification guide or the smallest meaningful local verification.

## Practical Default

When in doubt: clarify ambiguity, choose the fast path or plan path by risk, check relevant docs, make the smallest viable change, verify it, and record the outcome.
