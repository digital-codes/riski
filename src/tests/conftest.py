import sys, os

import pytest

# Ensure the repository root is on sys.path so that `import src` works during tests
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Load .env (RW_USER / RW_PWD) into the environment – never committed to git
_env_path = os.path.join(repo_root, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: requires live database / LLM endpoints"
    )
    config.addinivalue_line(
        "markers", "unit: mocked, no network / live endpoints required"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless RW credentials are available."""
    have_rw = bool(os.getenv("RW_USER")) and bool(os.getenv("RW_PWD"))
    if have_rw:
        return
    skip = pytest.mark.skip(reason="integration test: RW_USER/RW_PWD not configured in .env")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
