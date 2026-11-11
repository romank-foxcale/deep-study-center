"""Check that every resource URL answers, and that every LeetCode problem exists, is free and has
the title and difficulty the curriculum says. Needs network; not part of the test suite."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .plan import Curriculum

UA = "Mozilla/5.0 (deep-study-center link check)"
QUERY = "query q($s: String!) { question(titleSlug: $s) { title difficulty isPaidOnly } }"


def check_url(url: str) -> tuple[str, str]:
    """('ok' | 'warn' | 'fail', detail). Sites that block scripts or fail TLS locally are warnings."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return "ok", str(r.status)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 406, 429):
            return "warn", f"HTTP {e.code} (the site blocks scripts; open it in a browser)"
        return "fail", f"HTTP {e.code}"
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLError):
            return "warn", f"TLS error on this machine: {e.reason}"
        return "fail", str(e.reason)
    except Exception as e:  # timeouts and resets
        return "warn", f"{type(e).__name__}: {e}"


def check_problem(slug: str, title: str, difficulty: str) -> tuple[str, str]:
    body = json.dumps({"query": QUERY, "variables": {"s": slug}}).encode()
    req = urllib.request.Request("https://leetcode.com/graphql", body, {
        "Content-Type": "application/json", "Referer": "https://leetcode.com", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            q = json.load(r)["data"]["question"]
    except Exception as e:
        return "warn", f"LeetCode API not reachable: {e}"
    if q is None:
        return "fail", "no such problem"
    problems = []
    if q["title"] != title:
        problems.append(f"title is '{q['title']}'")
    if q["difficulty"].lower() != difficulty:
        problems.append(f"difficulty is {q['difficulty']}")
    if q["isPaidOnly"]:
        problems.append("premium only")
    return ("fail", "; ".join(problems)) if problems else ("ok", "")


def check_all(cur: Curriculum, leetcode: bool = True) -> int:
    jobs = [(f"resource {k}", check_url, (r.url,)) for k, r in cur.resources.items()]
    if leetcode:
        for u in cur.units.values():
            if u.kind == "problem":
                jobs.append((f"problem {u.id}", check_problem, (u.id[4:], u.title, u.difficulty)))
    counts = {"ok": 0, "warn": 0, "fail": 0}
    with ThreadPoolExecutor(8) as pool:
        results = pool.map(lambda j: (j[0], *j[1](*j[2])), jobs)
        for name, status, detail in results:
            counts[status] += 1
            if status != "ok":
                print(f"{status.upper():4} {name}: {detail}")
    print(f"\n{counts['ok']} ok, {counts['warn']} warnings, {counts['fail']} failures ({len(jobs)} checked).")
    return 1 if counts["fail"] else 0
