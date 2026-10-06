#!/usr/bin/env python3
"""
repo_location.py -- resolve/persist the local filesystem path to the
user's clone of the ubiquity-skills GitHub mirror
(https://github.com/FilterLabsAI/ubiquity-skills), so nothing in this
skill has to hardcode a path like `~/filterlabs/ubiquity-skills`. The
clone can live anywhere on disk and can be moved later -- this script
is the single source of truth for "where is it right now".

Config lives OUTSIDE both the git repo itself and this skill's own
synced directory, at ~/.hermes/state/ubiquity-skills-repo.json, so it:
  - never gets swept into a skill-content commit (it's not inside the
    repo being tracked, and it's not inside the Hermes skill directory
    either, so a `skill_manage` update to this skill can't clobber it)
  - survives moving the repo (just re-run --set with the new path)
  - is per-machine/per-user, not shared via git

Usage:
    python3 repo_location.py --get
        Prints the configured absolute path and exits 0 ONLY if a path
        is on file AND that directory still exists AND is a git repo
        AND its origin remote points at FilterLabsAI/ubiquity-skills.
        Otherwise prints nothing to stdout, a reason to stderr, exits 1.

    python3 repo_location.py --set <absolute_path>
        Validates <absolute_path> with the same checks as --get, and
        only on success persists it to the config file and exits 0.
        Exits 1 (nothing persisted) if validation fails -- prints why.

    python3 repo_location.py --status
        Prints a JSON object with the configured path (if any) and the
        result of each individual validation check, for diagnosing why
        --get is failing. Always exits 0.

Agent-facing contract: never assume a fixed path for the repo clone.
Always resolve it via `--get` first; if that exits 1, ask the user (via
`clarify`) for the absolute path to their clone -- offering to run
`git clone git@github.com:FilterLabsAI/ubiquity-skills.git <path>` for
them if they don't have one yet -- then persist it with `--set`.
"""
import argparse
import json
import os
import subprocess
import sys

CONFIG_PATH = os.path.expanduser("~/.hermes/state/ubiquity-skills-repo.json")
EXPECTED_REMOTE_SUBSTR = "FilterLabsAI/ubiquity-skills"


def _load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(d):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(d, f, indent=2)


def _git_remote_url(path):
    try:
        out = subprocess.run(
            ["git", "-C", path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def validate(path):
    """Returns (ok: bool, checks: dict, reason: str|None)."""
    checks = {
        "path_set": bool(path),
        "path_exists": False,
        "is_git_repo": False,
        "remote_matches": False,
        "remote_url": None,
    }
    if not path:
        return False, checks, "no path given"
    path = os.path.expanduser(path)
    checks["path_exists"] = os.path.isdir(path)
    if not checks["path_exists"]:
        return False, checks, f"directory does not exist: {path}"
    checks["is_git_repo"] = os.path.isdir(os.path.join(path, ".git"))
    if not checks["is_git_repo"]:
        return False, checks, f"not a git repo (no .git dir): {path}"
    remote = _git_remote_url(path)
    checks["remote_url"] = remote
    checks["remote_matches"] = bool(remote) and EXPECTED_REMOTE_SUBSTR in remote
    if not checks["remote_matches"]:
        return False, checks, (
            f"origin remote ({remote!r}) does not point at "
            f"{EXPECTED_REMOTE_SUBSTR}"
        )
    return True, checks, None


def cmd_get():
    cfg = _load_config()
    path = cfg.get("repo_path")
    ok, checks, reason = validate(path)
    if ok:
        print(os.path.expanduser(path))
        return 0
    print(reason or "no repo path configured yet", file=sys.stderr)
    return 1


def cmd_set(path):
    ok, checks, reason = validate(path)
    if not ok:
        print(f"refusing to save -- {reason}", file=sys.stderr)
        return 1
    cfg = _load_config()
    cfg["repo_path"] = os.path.abspath(os.path.expanduser(path))
    _save_config(cfg)
    print(f"Saved repo path: {cfg['repo_path']}")
    return 0


def cmd_status():
    cfg = _load_config()
    path = cfg.get("repo_path")
    ok, checks, reason = validate(path)
    print(json.dumps({
        "config_path": CONFIG_PATH,
        "configured_repo_path": path,
        "valid": ok,
        "reason": reason,
        "checks": checks,
    }, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--get", action="store_true")
    g.add_argument("--set", metavar="PATH")
    g.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.get:
        sys.exit(cmd_get())
    elif args.set:
        sys.exit(cmd_set(args.set))
    elif args.status:
        sys.exit(cmd_status())


if __name__ == "__main__":
    main()
