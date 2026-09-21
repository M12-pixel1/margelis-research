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
PLATFORMS = ("manylinux", "win_amd64", "macosx")

HEADER = """# Hash-pinned lock of tools/requirements.txt and its transitive dependencies.
# Generated from the PyPI JSON API (file digests) for CPython 3.14 on manylinux (x86_64,
# aarch64), win_amd64 and macOS (x86_64, arm64) plus pure-Python wheels and sdists. Install with:
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
            for m in re.finditer(r"(?m)^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)(?:;[^\\\n]*)? \\$",
                                 LOCK.read_text(encoding="utf-8"))}


def _wanted(filename: str) -> bool:
    if filename.endswith(".tar.gz"):
        return True
    if not filename.endswith(".whl"):
        return False
    if "py3-none-any" in filename:
        return True
    return (PY_TAG in filename or "abi3" in filename) and any(p in filename for p in PLATFORMS) \
        and any(arch in filename for arch in ("x86_64", "win_amd64", "arm64", "aarch64", "universal2"))


PY_VERSION = (3, 14)  # the interpreter the lock targets (CI pins python-version 3.14)
_VERSION_MARKER = re.compile(r'\s*(python_version|python_full_version)\s*(<=|>=|==|!=|<|>)\s*"([0-9.]+)"\s*')


def _version_marker(marker: str) -> bool | None:
    """Decide a marker that only compares the interpreter version; None when it is another kind."""
    m = _VERSION_MARKER.fullmatch(marker)
    if not m:
        return None
    want = tuple(int(x) for x in m.group(3).split("."))
    have = (PY_VERSION + (0,))[:len(want)]
    return {"<": have < want, "<=": have <= want, "==": have == want,
            "!=": have != want, ">": have > want, ">=": have >= want}[m.group(2)]


def _requirements(requires_dist: list[str]) -> list[tuple[str, str | None]]:
    """(name, marker) of the runtime requirements a plain `pip install` pulls on the target interpreter.

    Extras are skipped. Interpreter-version markers are decided against PY_VERSION. Every other
    marker (platform, implementation) is carried verbatim into the lock so pip applies it per
    platform: leaving such a dependency out would break a --require-hashes install.
    """
    out = []
    for spec in requires_dist or []:
        req, _, marker = spec.partition(";")
        marker = " ".join(marker.split())
        m = re.match(r"\s*([A-Za-z0-9_.\-]+)", req)
        if not m:
            continue
        if marker:
            if re.search(r"\bextra\s*==", marker):
                continue
            decided = _version_marker(marker)
            if decided is False:
                continue
            if decided is True:
                marker = ""
        out.append((_norm(m.group(1)), marker or None))
    return out


def resolve(pins: dict[str, str]) -> dict[str, dict]:
    """Walk transitive dependencies; every dependency must already be pinned (in the lock or requirements)."""
    known = dict(pins)
    known.update({k: v for k, v in lock_pins().items() if k not in known})
    out: dict[str, dict] = {}
    markers: dict[str, str | None] = dict.fromkeys(pins)
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
        out[name] = {"version": version, "files": files, "marker": markers.get(name)}
        for dep, marker in _requirements(data["info"].get("requires_dist") or []):
            if dep in markers:
                if marker is None or markers[dep] is None:
                    markers[dep] = None  # unconditional on at least one path
                elif marker != markers[dep]:
                    markers[dep] = f"({markers[dep]}) or ({marker})"
            else:
                markers[dep] = marker
            if dep in out:
                out[dep]["marker"] = markers[dep]
            elif dep not in queue:
                queue.append(dep)
    return out


def render(resolved: dict[str, dict]) -> str:
    lines = [HEADER]
    for name in sorted(resolved):
        e = resolved[name]
        marker = f"; {e['marker']}" if e.get("marker") else ""
        lines.append(f"{name}=={e['version']}{marker} \\")
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
