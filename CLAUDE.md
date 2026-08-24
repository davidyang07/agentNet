`docs/SPEC.md` is the authoritative product/technical specification. `docs/BRIEF.md` provides project motivation and broader context. If they conflict, follow SPEC.

- Implement only the phase/scope explicitly requested by the user. Do not speculatively implement functionality assigned to future phases.
- Prefer the simplest architecture and smallest dependency set that satisfies the current requirements. Do not add dependencies without a concrete requirement.
- Do not weaken, delete, skip, or rewrite tests merely to make an implementation pass.
- Run the relevant tests, linting, type checking, and other available verification before claiming work is complete. Never claim something works based only on inspection when it can reasonably be executed or tested.
- Never commit secrets, credentials, API keys, `.env` files, generated credentials, or local machine configuration.
- Treat Linux/WSL as the canonical local development environment.
- Preserve documented architectural boundaries.
- If implementation requires deviating materially from SPEC, stop and surface the deviation and rationale before making it.
- Prefer small, reviewable changes over unrelated cleanup or refactoring. Do not change unrelated files while completing a scoped task.
