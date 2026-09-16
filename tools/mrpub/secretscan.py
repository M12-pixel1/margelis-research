"""Pre-publication scan for credentials and private operational data.

This is a deliberately strict, dependency-free scanner. It complements (does not
replace) GitHub secret scanning and push protection on the public repository.
Patterns are written so that this file does not match itself.
"""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path

from .common import ROOT, git

PATTERNS: dict[str, re.Pattern] = {
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]{0,20}PRIVATE KEY" + "-----"),
    "slack-token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "stripe-live-key": re.compile(r"\b[rs]k_live_[A-Za-z0-9]{16,}"),
    "anthropic-key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai-style-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}"),
    "google-api-key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"),
    "telegram-bot-token": re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    "credential-assignment": re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|bearer)\b"
        r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+_=\-]{16,}"),
    "private-filesystem-path": re.compile(r"(?i)(?:\b[a-z]:\\user[s]\\|/hom[e]/[a-z]|/var/ww[w]/|/etc/cadd[y]|/op[t]/[a-z]|/roo[t]/)"),
    "internal-subdomain": re.compile(r"(?i)\b[a-z0-9-]+\.rupestelis\.co[m]\b"),
    "email-address": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "phone-number": re.compile(r"(?<![\w.])\+\d[\d \-]{7,}\d\b"),
}

IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
ALLOWED_IPS = {"127.0.0.1", "0.0.0.0"}
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]

SKIP_SUFFIXES = {".ttf", ".png", ".pdf", ".woff", ".woff2", ".ico", ".jpg", ".jpeg"}


def candidate_files() -> list[Path]:
    """Tracked + untracked-but-not-ignored files (what a `git add -A` would publish)."""
    out = git("ls-files", "--cached", "--others", "--exclude-standard", check=False)
    if out:
        return [ROOT / p for p in out.splitlines() if (ROOT / p).is_file()]
    return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


def scan_text(text: str) -> list[tuple[int, str, str]]:
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, pat in PATTERNS.items():
            for m in pat.finditer(line):
                findings.append((lineno, name, m.group(0)))
        for m in IPV4.finditer(line):
            try:
                ip = ipaddress.ip_address(m.group(0))
            except ValueError:
                continue
            if m.group(0) in ALLOWED_IPS or any(ip in n for n in DOC_NETS):
                continue
            findings.append((lineno, "ipv4-address", m.group(0)))
    return findings


def redact(value: str) -> str:
    return value if len(value) <= 8 else f"{value[:4]}…{value[-2:]} ({len(value)} chars)"


def scan(paths: list[Path] | None = None) -> list[str]:
    problems = []
    for path in paths or candidate_files():
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for lineno, name, value in scan_text(text):
            rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
            problems.append(f"{rel}:{lineno}: {name}: {redact(value)}")
    return problems
