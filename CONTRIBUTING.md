# Contributing to YouTube Producer

Thank you for improving YouTube Producer.

## Before you start

1. Search existing issues and describe a substantial change in an issue before implementing it.
2. Keep each pull request focused on one user problem.
3. Never commit API keys, `.env` files, recordings containing private channel data, or other personal data.

## Development checks

Use Python 3.12 or newer. Before opening a pull request, install the development dependencies and run the tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Please preserve the project principle: the tool prepares analysis and drafts, while publication decisions stay with the user.
