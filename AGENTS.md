# AGENTS.md

Codex operating guidelines for this repository. These rules are intended to reduce common LLM coding mistakes while keeping execution practical.

Use judgment for trivial tasks. These guidelines bias toward correctness, clarity, and minimal diffs over speed.

## 1. Think Before Coding

Do not silently guess.

- State assumptions when they materially affect the implementation.
- If the request is ambiguous and there are multiple reasonable interpretations, surface them instead of picking one silently.
- If a simpler or safer path exists, say so before implementing.
- If you are blocked by missing requirements, ask a short clarifying question instead of inventing behavior.

## 2. Prefer Simple Solutions

Implement the smallest change that fully solves the requested problem.

- Do not add features, options, abstractions, or configurability that were not requested.
- Do not generalize for hypothetical future use.
- Avoid introducing new layers, helpers, or patterns for one-off logic.
- If the same result can be achieved with materially less code, prefer the shorter version.

## 3. Make Surgical Changes

Keep diffs tightly scoped to the task.

- Touch only files and lines that are needed for the requested outcome.
- Do not refactor adjacent code unless the task requires it.
- Match the surrounding style and conventions of the repository.
- Do not remove unrelated dead code, comments, or formatting noise just because you noticed it.
- Clean up only issues directly created by your own change, such as unused imports you introduced.

## 4. Work Backward From Verification

Define success in a way that can be checked.

- For bug fixes, prefer reproducing the issue first, then fixing it.
- For new behavior, prefer adding or updating tests when the repo already uses tests.
- For refactors, preserve behavior and verify before and after when practical.
- End work by running the smallest meaningful verification available, such as targeted tests, lint, build, or a focused manual check.

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

## Practical Default

When in doubt:

1. Clarify ambiguity
2. Choose the simplest viable implementation
3. Keep the diff narrow
4. Verify the result
