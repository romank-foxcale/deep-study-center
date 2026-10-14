import pytest

from dsc.db import DB
from dsc.jobs import Jobs
from dsc.providers import ProviderUnavailable
from dsc.seed import seed_demo


class FakeRunner:
    """Stands in for the agent CLIs. `responses[role]` is a value or a callable(call) -> value."""

    def __init__(self):
        self.calls = []
        self.responses = {}
        self.unavailable = False

    def __call__(self, route, call, cwd):
        self.calls.append((route["role"], call))
        if self.unavailable:
            raise ProviderUnavailable("offline (test)")
        r = self.responses[route["role"]]
        return (r(call) if callable(r) else r), route["provider"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DSC_WORKSPACE", str(tmp_path))
    db = DB(tmp_path / "study.db")
    seed_demo(db)
    runner = FakeRunner()
    jobs = Jobs(db, runner=runner, inline=True)
    return db, jobs, runner
