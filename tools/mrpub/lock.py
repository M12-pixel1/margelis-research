"""tools/requirements.lock: hash-pinned versions of requirements.txt and its transitive dependencies.

The lock is generated from the PyPI JSON API (per-file sha256 digests) so that CI installs
with --require-hashes and a tampered or substituted package cannot be installed silently.
"""
from __future__ import annotations

import re

import requests

from .common import TOOLS, PipelineError, write_text

REQUIREMENTS = TOOLS / "requirements.txt"
LOCK = TOOLS / "requirements.lock"
PYPI = "https://pypi.org/pypi/{name}/{version}/json"
PY_TAG = "cp314"
PLATFORMS = ("manylinux", "win_amd64")

HEADER = """# Hash-pinned lock of tools/requirements.txt and its transitive dependencies.
# Generated from the PyPI JSON API (file digests) for CPython 3.14 on manylinux x86_64 and
# win_amd64 plus pure-Python wheels and sdists. Install with:
#   python -m pip install --require-hashes -r tools/requirements.lock
# Regenerate with: python tools/publish.py lock   (after changing tools/requirements.txt)
"""


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def direct_pins() -> dict[str, str]:
    pins = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)", line)
        if not m:
            raise PipelineError(f"requirements.txt: only exact pins (name==version) are allowed, got {line!r}")
        pins[_norm(m.group(1))] = m.group(2)
    return pins


def lock_pins() -> dict[str, str]:
    if not LOCK.exists():
        return {}
    return {_norm(m.group(1)): m.group(2)
            for m in re.finditer(r"(?m)^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)", LOCK.read_text(encoding="utf-8"))}


def _wanted(filename: str) -> bool:
    if filename.endswith(".tar.gz"):
        return True
    if not filename.endswith(".whl"):
        return False
    if "py3-none-any" in filename:
        return True
    return (PY_TAG in filename or "abi3" in filename) and any(p in filename for p in PLATFORMS) \
        and ("x86_64" in filename or "win_amd64" in filename)


def _requirement_names(requires_dist: list[str]) -> list[str]:
    """Names of unconditional runtime requirements (extras and environment markers are skipped)."""
    names = []
    for spec in requires_dist or []:
        if ";" in spec:  # extras / markers: not installed by a plain `pip install`
            continue
        m = re.match(r"\s*([A-Za-z0-9_.\-]+)", spec)
        if m:
            names.append(_norm(m.group(1)))
    return names


def resolve(pins: dict[str, str]) -> dict[str, dict]:
    """Walk transitive dependencies; every dependency must already be pinned (in the lock or requirements)."""
    known = dict(pins)
    known.update({k: v for k, v in lock_pins().items() if k not in known})
    out: dict[str, dict] = {}
    queue = list(pins)
    while queue:
        name = queue.pop(0)
        if name in out:
            continue
        version = known.get(name)
        if not version:
            raise PipelineError(f"dependency {name} has no pinned version; add it to requirements.txt")
        r = requests.get(PYPI.format(name=name, version=version), timeout=60)
        if r.status_code != 200:
            raise PipelineError(f"PyPI has no {name}=={version} (HTTP {r.status_code})")
        data = r.json()
        files = sorted((f["filename"], f["digests"]["sha256"]) for f in data["urls"] if _wanted(f["filename"]))
        if not files:
            raise PipelineError(f"{name}=={version}: no wheel or sdist for the supported platforms")
        out[name] = {"version": version, "files": files}
        queue += [d for d in _requirement_names(data["info"].get("requires_dist") or []) if d not in out]
    return out


def render(resolved: dict[str, dict]) -> str:
    lines = [HEADER]
    for name in sorted(resolved):
        e = resolved[name]
        lines.append(f"{name}=={e['version']} \\")
        for i, (_, digest) in enumerate(e["files"]):
            tail = " \\" if i < len(e["files"]) - 1 else ""
            lines.append(f"    --hash=sha256:{digest}{tail}")
    return "\n".join(lines) + "\n"


def write_lock() -> dict[str, dict]:
    resolved = resolve(direct_pins())
    write_text(LOCK, render(resolved))
    return resolved


def check() -> tuple[bool, str]:
    """Every direct pin must appear in the lock with the same version; the lock must carry hashes."""
    direct, locked = direct_pins(), lock_pins()
    if not LOCK.exists():
        return False, "tools/requirements.lock missing (run `publish.py lock`)"
    drift = [f"{n}: requirements {v} vs lock {locked.get(n)}" for n, v in direct.items() if locked.get(n) != v]
    if drift:
        return False, "; ".join(drift)
    text = LOCK.read_text(encoding="utf-8")
    without_hash = [n for n in locked if not re.search(rf"(?m)^{re.escape(n)}==.*\\\n(\s+--hash=sha256:[0-9a-f]{{64}}.*\n)+", text)]
    if without_hash:
        return False, f"lock entries without hashes: {without_hash}"
    return True, f"{len(locked)} packages hash-pinned; direct pins match requirements.txt"
