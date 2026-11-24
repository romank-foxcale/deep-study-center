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


@pytest.fixture(autouse=True)
def keep_option_order(monkeypatch):
    """Fixtures put the right option first; tests of the shuffle turn it back on."""
    from dsc import mcq
    monkeypatch.setattr(mcq, "SHUFFLE", False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never fetch a link (SPEC §47); a test that reads one patches these with its own page or captions."""
    from dsc import links

    def offline(*_a, **_k):
        raise links.LinkError("no network in tests")
    monkeypatch.setattr(links, "_fetch", offline)
    monkeypatch.setattr(links, "transcript", offline)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DSC_WORKSPACE", str(tmp_path))
    db = DB(tmp_path / "study.db")
    seed_demo(db)
    db.set_meta("auto_research", "0")  # tests that want research-ahead turn it on explicitly
    db.set_meta("auto_refresh", "0")   # same for card refresh
    db.set_meta("formula_notes", "0")  # same for the formula hover notes
    db.set_meta("auto_gaps", "0")      # same for the gap search after a book is mapped
    runner = FakeRunner()
    jobs = Jobs(db, runner=runner, inline=True)
    return db, jobs, runner
