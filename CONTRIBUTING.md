# Contributing

Thank you for improving Prompt Architect Agent.

1. Fork the repository and create a focused branch.
2. Install development dependencies with `python -m pip install -e ".[web,dev]"` and `npm ci --prefix frontend`.
3. Keep rules in YAML, templates in Jinja files, orchestration logic in Python, and workbench code in `frontend/`.
4. Add or update tests for every behavior change.
5. Run `pytest`, `npm test --prefix frontend`, and `npm run build --prefix frontend` before opening a pull request.

Pull requests should explain the behavior change, validation performed, and any compatibility impact. Never add real API keys, tokens, passwords, or private prompt content to fixtures or issues.
