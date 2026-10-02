#!/usr/bin/env python3
"""
scan_for_leaks.py -- scan files/dirs for things that shouldn't be
committed to a shared skills repo: emails, UUIDs, bearer tokens/JWTs,
API keys/secrets/passwords, AWS access key IDs, PEM private keys, and
internal-looking hostnames/IPs.

Usage:
    python3 scan_for_leaks.py <file_or_dir> [<file_or_dir> ...]
    python3 scan_for_leaks.py --json <file_or_dir> ...

Exit code: 0 if no findings, 1 if any findings (so it can gate a script).
This is a HEURISTIC scanner -- false positives/negatives are expected.
Always have a human review the findings list before deciding what to
redact; never auto-redact without the user's go-ahead.
"""
import argparse
import json
import os
import re
import sys

# Directories/files to skip entirely.
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz",
            ".ico", ".woff", ".woff2", ".ttf", ".eot"}

# (kind, severity, compiled regex)
# severity: "high" = must redact/remove before commit; "medium" = review;
# "low" = usually fine but worth a glance.
PATTERNS = [
    ("pem_private_key", "high",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("jwt_or_bearer_token", "high",
     re.compile(r"(?:Bearer\s+)?eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("aws_access_key_id", "high",
     re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("generic_secret_assignment", "high",
     re.compile(r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-/+=]{8,}[\"']?")),
    ("email", "medium",
     re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("uuid", "medium",
     re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("ipv4", "low",
     re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|1?\d{1,2})\b")),
    ("internal_hostname", "low",
     re.compile(r"\b[a-zA-Z0-9.-]*\.(?:filterlabs\.ai|internal|local)\b")),
]

# Reduce noise: common placeholder/example values that should NOT be flagged.
ALLOWLIST_SNIPPETS = {
    "user@example.com", "you@example.com", "test@example.com",
    "00000000-0000-0000-0000-000000000000",
}


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in files:
                    if os.path.splitext(f)[1].lower() in SKIP_EXT:
                        continue
                    yield os.path.join(root, f)


def scan_file(path):
    findings = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return findings
    for lineno, line in enumerate(lines, start=1):
        for kind, severity, pattern in PATTERNS:
            for m in pattern.finditer(line):
                snippet = m.group(0)
                if snippet in ALLOWLIST_SNIPPETS:
                    continue
                findings.append({
                    "file": path,
                    "line": lineno,
                    "kind": kind,
                    "severity": severity,
                    "snippet": snippet.strip(),
                })
    return findings


def suggest_fix(kind):
    return {
        "email": "replace with a placeholder like user@example.com, or <REDACTED_EMAIL>",
        "uuid": "replace with a generic placeholder like <PIPELINE_UUID>/<FEED_ID>/<ENTITY_ID>, or remove the example",
        "jwt_or_bearer_token": "MUST remove/redact -- never commit a token even if expired",
        "aws_access_key_id": "MUST remove/redact immediately and rotate the key",
        "pem_private_key": "MUST remove entirely -- never commit private key material",
        "generic_secret_assignment": "MUST remove/redact the value; keep only the variable name if needed for docs",
        "ipv4": "replace with a placeholder like 203.0.113.5 (TEST-NET-3) if an example IP is needed",
        "internal_hostname": "replace with a generic placeholder like your-env.example.com",
    }.get(kind, "review and redact if sensitive")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", help="files or directories to scan")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    all_findings = []
    for f in iter_files(args.paths):
        all_findings.extend(scan_file(f))

    if args.json:
        print(json.dumps(all_findings, indent=2))
    else:
        if not all_findings:
            print("No findings. Clean.")
        else:
            print(f"{len(all_findings)} finding(s):\n")
            print(f"{'#':<4}{'file:line':<40}{'kind':<24}{'sev':<8}snippet")
            for i, f in enumerate(all_findings, start=1):
                loc = f"{f['file']}:{f['line']}"
                print(f"{i:<4}{loc:<40}{f['kind']:<24}{f['severity']:<8}{f['snippet'][:60]}")
            print()
            print("Suggested fixes:")
            for i, f in enumerate(all_findings, start=1):
                print(f"  {i}. {suggest_fix(f['kind'])}")

    sys.exit(1 if all_findings else 0)


if __name__ == "__main__":
    main()
