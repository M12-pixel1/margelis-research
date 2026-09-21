"""Unit tests for the dependency-lock resolver: environment markers and lock-line parsing.

Why: the resolver once skipped every marker-bearing requirement, so `cryptography`'s CPython-only
`cffi` dependency was left out of the lock and a `--require-hashes` install would have failed on a
clean runner. Exit status 1 on any failure.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrpub import lock  # noqa: E402

FAILURES: list[str] = []


def expect(cond: bool, label: str) -> None:
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILURES.append(label)


def main() -> int:
    reqs = lock._requirements([
        'cffi>=2.0.0; platform_python_implementation != "PyPy"',
        'typing-extensions>=4.13.2; python_full_version < "3.11"',
        'bcrypt>=3.1.5; extra == "ssh"',
        "pycparser",
        'tomli>=1.1; python_version < "3.11"',
        'colorama; sys_platform == "win32"',
        'backports-zoneinfo; python_version < "3.9" and sys_platform == "linux"',
        'importlib-metadata; python_version >= "3.8"',
    ])
    got = dict(reqs)
    expect(got.get("cffi") == 'platform_python_implementation != "PyPy"',
           "implementation marker is carried verbatim (cffi)")
    expect("typing-extensions" not in got, "python_full_version < 3.11 is decided false on 3.14")
    expect("tomli" not in got, "python_version < 3.11 is decided false on 3.14")
    expect("bcrypt" not in got, "extras are skipped")
    expect(got.get("pycparser", "x") is None, "unconditional requirement has no marker")
    expect(got.get("colorama") == 'sys_platform == "win32"', "platform marker is carried verbatim")
    expect(got.get("backports-zoneinfo", "x") == 'python_version < "3.9" and sys_platform == "linux"',
           "compound marker is carried verbatim (never silently dropped)")
    expect("importlib-metadata" in got and got["importlib-metadata"] is None,
           "python_version >= 3.8 is decided true and the marker is dropped")

    rendered = lock.render({
        "cffi": {"version": "2.1.1", "marker": 'platform_python_implementation != "PyPy"',
                 "files": [("a.whl", "0" * 64), ("b.whl", "1" * 64)]},
        "pycparser": {"version": "3.0", "marker": None, "files": [("c.whl", "2" * 64)]},
    })
    bs = "\\"
    expect(f'cffi==2.1.1; platform_python_implementation != "PyPy" {bs}\n    --hash=sha256:' + "0" * 64 + f" {bs}\n" in rendered,
           "marker is rendered on the pin line before the hash continuation")
    expect(f"pycparser==3.0 {bs}\n    --hash=sha256:" + "2" * 64 + "\n" in rendered, "unconditional pin renders as before")

    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "requirements.lock"
        fake.write_text(rendered, encoding="utf-8")
        original = lock.LOCK
        lock.LOCK = fake
        try:
            pins = lock.lock_pins()
        finally:
            lock.LOCK = original
    expect(pins == {"cffi": "2.1.1", "pycparser": "3.0"}, "lock_pins parses pins with and without markers")

    ok, detail = lock.check()
    expect(ok, f"the committed lock is consistent with requirements.txt ({detail})")
    real = lock.LOCK.read_text(encoding="utf-8")
    for name in ("cryptography", "cffi", "pycparser"):
        expect(f"\n{name}==" in real, f"committed lock pins {name} (needed by the Stripe signed-action test)")

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall lock resolver tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
