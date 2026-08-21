"""Tests for GitHub Actions workflow files in oriz-ipo.

Validates structure, security, and consistency of CI/CD workflows.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _load(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _workflow_files() -> list[str]:
    if not WORKFLOWS_DIR.exists():
        return []
    return [f.name for f in WORKFLOWS_DIR.iterdir() if f.suffix in (".yml", ".yaml")]


# ── Structure ────────────────────────────────────────────────────────

class TestWorkflowStructure:
    """Basic YAML structure checks."""

    @pytest.fixture(params=_workflow_files())
    def yaml_text(self, request: pytest.FixtureRequest) -> str:
        return _load(request.param)

    def test_has_name(self, yaml_text: str) -> None:
        assert re.search(r"^name:\s+", yaml_text, re.MULTILINE)

    def test_has_on_trigger(self, yaml_text: str) -> None:
        assert re.search(r"^on:", yaml_text, re.MULTILINE)

    def test_has_jobs(self, yaml_text: str) -> None:
        assert re.search(r"^jobs:", yaml_text, re.MULTILINE)

    def test_has_concurrency_or_is_simple_ci(self, yaml_text: str) -> None:
        # Simple CI workflows (push/PR only) may omit concurrency.
        # Scheduled/automated workflows should have it.
        has_schedule = 'schedule:' in yaml_text
        has_concurrency = bool(re.search(r"^concurrency:", yaml_text, re.MULTILINE))
        if has_schedule:
            assert has_concurrency, 'Scheduled workflows should have concurrency'


# ── ci.yml ──────────────────────────────────────────────────────────

class TestCiYml:
    @pytest.fixture(scope="class")
    def yaml(self) -> str:
        return _load("ci.yml")

    def test_triggers_on_push_and_pr(self, yaml: str) -> None:
        assert "push:" in yaml
        assert "pull_request:" in yaml

    def test_uses_checkout_v4(self, yaml: str) -> None:
        assert "actions/checkout@v4" in yaml

    def test_python_job_runs_tests(self, yaml: str) -> None:
        assert "pytest" in yaml

    def test_web_job_builds(self, yaml: str) -> None:
        assert "npm run build" in yaml or "npm ci" in yaml

    def test_read_only_permissions(self, yaml: str) -> None:
        assert "contents: read" in yaml

    def test_no_hardcoded_secrets(self, yaml: str) -> None:
        assert not re.search(r"ghp_[A-Za-z0-9]{36}", yaml)
        assert not re.search(r"sk-[A-Za-z0-9]{48}", yaml)


# ── scrape.yml (ipo-gmp-watch) ──────────────────────────────────────

class TestScrapeYml:
    @pytest.fixture(scope="class")
    def yaml(self) -> str:
        return _load("scrape.yml")

    def test_named_ipo_gmp_watch(self, yaml: str) -> None:
        assert "ipo-gmp-watch" in yaml

    def test_has_schedule_cron(self, yaml: str) -> None:
        assert "schedule:" in yaml
        assert "cron:" in yaml

    def test_has_write_permissions_for_data_commit(self, yaml: str) -> None:
        assert "contents: write" in yaml

    def test_has_concurrency_group(self, yaml: str) -> None:
        assert "ipo-scrape" in yaml

    def test_installs_playwright(self, yaml: str) -> None:
        assert "playwright install chromium" in yaml

    def test_runs_tests_before_scrape(self, yaml: str) -> None:
        # Test step should come before scrape step
        test_pos = yaml.find("Run tests")
        scrape_pos = yaml.find("ipo_watch") or yaml.find("--data")
        if test_pos >= 0 and scrape_pos >= 0:
            assert test_pos < scrape_pos

    def test_commits_data(self, yaml: str) -> None:
        assert "git commit" in yaml
        assert "git push" in yaml

    def test_telegram_failure_alert(self, yaml: str) -> None:
        assert "Alert on failure" in yaml
        assert "TELEGRAM_BOT_TOKEN" in yaml

    def test_uses_secrets_not_hardcoded(self, yaml: str) -> None:
        # Telegram tokens should be from secrets
        assert "secrets.TELEGRAM_BOT_TOKEN" in yaml
        assert not re.search(r'"[0-9]{8,10}:[A-Za-z0-9_-]{35}"', yaml)

    def test_no_hardcoded_secrets(self, yaml: str) -> None:
        assert not re.search(r"ghp_[A-Za-z0-9]{36}", yaml)
        assert not re.search(r"sk-[A-Za-z0-9]{48}", yaml)

    def test_timeout_minutes_set(self, yaml: str) -> None:
        assert "timeout-minutes:" in yaml


# ── Cross-workflow consistency ───────────────────────────────────────

class TestCrossWorkflowConsistency:
    def test_all_use_checkout_v4(self) -> None:
        for name in _workflow_files():
            yaml = _load(name)
            assert "actions/checkout@v4" in yaml, f"{name} missing checkout@v4"

    def test_scheduled_workflows_have_concurrency(self) -> None:
        for name in _workflow_files():
            yaml = _load(name)
            if 'schedule:' in yaml:
                assert re.search(r"^concurrency:", yaml, re.MULTILINE), \
                    f"{name} (scheduled) missing concurrency"

    def test_no_hardcoded_tokens_across_all(self) -> None:
        for name in _workflow_files():
            yaml = _load(name)
            assert not re.search(r"ghp_[A-Za-z0-9]{36}", yaml), \
                f"{name} has hardcoded GitHub PAT"
            assert not re.search(r"sk-[A-Za-z0-9]{48}", yaml), \
                f"{name} has hardcoded OpenAI key"
