"""Every environment variable the code reads must be declared in .env.example.

This exists because the gap is invisible until runtime and then misleading.
`GEMINI_API_KEY` was read by the CV parser but never declared, so a developer
who copied `.env.example` got a backend that started cleanly and failed the
moment they uploaded a CV. `GEMINI_MODEL` was worse: unset, the code defaults to
a model not every key can call, and `call_gemini` is designed never to raise, so
explanations silently degrade to a deterministic fallback that reads as weak
analysis rather than a misconfiguration.

A missing declaration is therefore a real defect, not a documentation nit.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCANNED_DIRS = ("backend", "streamlit_app", "scripts")

# os.getenv("X"), os.environ.get("X"), os.environ["X"]
ENV_READ = re.compile(
    r"""(?:getenv\(\s*|environ\.get\(\s*|environ\[\s*)["']([A-Z_0-9]+)["']"""
)
# Left-hand side of an assignment in .env.example, commented lines excluded.
ENV_DECLARED = re.compile(r"^([A-Z_0-9]+)=", re.MULTILINE)


def _env_vars_read() -> dict:
    """Map each variable name to the files that read it."""
    found = {}
    for directory in SCANNED_DIRS:
        for path in (REPO_ROOT / directory).rglob("*.py"):
            # Tests are skipped: they set env vars for their own purposes, and
            # that is not application configuration a developer must supply.
            if "__pycache__" in path.parts or "tests" in path.parts:
                continue
            for name in ENV_READ.findall(path.read_text(encoding="utf-8")):
                found.setdefault(name, set()).add(
                    str(path.relative_to(REPO_ROOT))
                )
    return found


def _env_vars_declared() -> set:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    return set(ENV_DECLARED.findall(text))


def test_every_env_var_read_is_declared():
    read = _env_vars_read()
    declared = _env_vars_declared()

    undeclared = {name: sorted(files) for name, files in read.items()
                  if name not in declared}

    assert not undeclared, (
        "These env vars are read by code but missing from .env.example, so a "
        f"developer copying it gets a silently misconfigured app: {undeclared}"
    )


def test_the_scan_actually_finds_things():
    """Guard against the regexes silently matching nothing, which would make
    the test above pass for the wrong reason."""
    read = _env_vars_read()

    assert "DATABASE_URL" in read
    assert "GEMINI_API_KEY" in read
    assert len(_env_vars_declared()) > 5


@pytest.mark.parametrize(
    "name",
    ["GEMINI_API_KEY", "GEMINI_MODEL", "RANKING_MODEL", "QDRANT_MODE",
     "DATABASE_URL"],
)
def test_critical_vars_are_declared(name):
    """Named explicitly: each of these has silently broken the app before."""
    assert name in _env_vars_declared()


def test_no_real_secret_is_committed_in_the_gemini_key():
    """The template must ship the key empty. A real key here goes to GitHub."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    match = re.search(r"^GEMINI_API_KEY=(.*)$", text, re.MULTILINE)

    assert match is not None
    assert match.group(1).strip() == "", (
        "GEMINI_API_KEY must be empty in .env.example; put real keys in .env, "
        "which is gitignored."
    )
