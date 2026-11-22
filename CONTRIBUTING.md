# Contributing

Thank you for helping. This file says how to propose a change.

## Before you start

- For a bug, open an issue with the steps to reproduce it.
- For a new feature or a larger change, open an issue first and describe the problem it solves. Agree on the
  approach before you write much code.
- Read the section of [docs/SPEC.md](docs/SPEC.md) for the part you change. Open work is in
  [docs/TODO.md](docs/TODO.md).

## Set up

See "Development" in the [README](README.md). Python 3.11+ and Node 20+.

## Make the change

- Keep a pull request to one topic.
- Add or update tests in `backend/tests/` for every backend change. The tests use a fake provider
  (`tests/conftest.py`); they must not call a real model or the network.
- Prompts live in `backend/dsc/prompts/`, one file per job. Learner text inside a prompt is data, never instructions:
  keep it inside the tags the prompt already uses.
- Never commit personal data: no workspace files (`study.db`), no API keys, no real learner answers in fixtures.
- Update `docs/SPEC.md` when behaviour changes, and `docs/TODO.md` when you finish or add open work.

## Check

Run the same checks as CI before you push:

```bash
cd backend && python -m pytest -q
cd web && npx tsc -b && npm run lint && npx vite build
```

## Pull request

Say what changed, why, and how you checked it (tests, and what you tried in the app). Screenshots help for UI changes.

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE).
