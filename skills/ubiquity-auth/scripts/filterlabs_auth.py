#!/usr/bin/env python3
"""
FilterLabs / Ubiquity OAuth token manager.

Stores tokens in ~/.hermes/secrets/filterlabs_tokens.json and refreshes
the access token automatically when it's near expiry, using the refresh_token
grant against Keycloak (auth.filterlabs.ai).

First-time use (or re-auth after refresh_token expiry, ~8h idle):
    python3 filterlabs_auth.py --login "email@example.com"
    (prompts for the password without echo; or pipe it with --password-stdin.
    The password is never accepted on the command line, so it cannot leak
    through `ps`, /proc/<pid>/cmdline or shell history.)

Library usage:
    from filterlabs_auth import get_access_token
    token = get_access_token()   # returns a valid access token, refreshing if needed

CLI:
    python3 filterlabs_auth.py            # prints a valid access token to stdout
    python3 filterlabs_auth.py --status   # prints expiry info (never the token)
    python3 filterlabs_auth.py --login EMAIL [--password-stdin]   # initial login / re-login
    python3 filterlabs_auth.py --help     # this text (never the token)

Any other argument is an error. Only the bare invocation prints a token, so
an agent that probes the script with `--help` or a guessed flag cannot spill
a live token into its transcript or logs.

Concurrency: refreshes are serialised with an exclusive lock on
<token file>.lock, and the file is re-read once the lock is held. Keycloak
rotates the refresh token on every use, so without the lock two processes
refreshing at the same moment would both send the same old refresh token and
the second would get invalid_grant.
"""
import contextlib
import getpass
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import fcntl
except ImportError:  # Windows has no fcntl. There the lock is a no-op, which
    # means parallel refreshes are not serialised; run one process at a time.
    fcntl = None

def _hermes_home():
    """Resolve the active profile's Hermes home directory.

    HERMES_HOME is set per-profile by the Hermes runtime (e.g.
    ~/.hermes/profiles/<profile>), so scoping secrets under it keeps each
    profile's Ubiquity session isolated. Falls back to ~/.hermes only when
    HERMES_HOME is unset (e.g. a bare script run outside any Hermes
    session) -- that fallback is NOT profile-safe and should only be hit
    outside normal agent operation.
    """
    val = os.environ.get("HERMES_HOME", "").strip()
    return val if val else os.path.expanduser("~/.hermes")


TOKEN_PATH = os.path.join(_hermes_home(), "secrets", "filterlabs_tokens.json")
LEEWAY_SECONDS = 120  # refresh if less than this much time remains

REALM = "filter-labs-web"
CLIENT_ID = "web-app"
TOKEN_URL = f"https://auth.filterlabs.ai/realms/{REALM}/protocol/openid-connect/token"


def _load():
    with open(TOKEN_PATH) as f:
        return json.load(f)


def _save(d):
    """Write atomically with owner-only permissions from the first byte.

    The temp file is created 0600 via mkstemp (never umask-dependent), then
    os.replace()d over the live file, so a crash mid-write cannot leave a
    truncated token file and no other local user can read it at any point."""
    secrets_dir = os.path.dirname(TOKEN_PATH)
    os.makedirs(secrets_dir, mode=0o700, exist_ok=True)
    os.chmod(secrets_dir, 0o700)
    fd, tmp = tempfile.mkstemp(dir=secrets_dir, prefix=".tokens.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(d, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, TOKEN_PATH)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def _locked():
    """Serialise refreshes across processes. Keycloak rotates the refresh
    token on every use, so two processes refreshing with the same old token
    means one of them gets invalid_grant; holding an exclusive lock and
    re-reading the file inside it makes the second caller see the first
    caller's fresh token instead."""
    secrets_dir = os.path.dirname(TOKEN_PATH)
    os.makedirs(secrets_dir, mode=0o700, exist_ok=True)
    if fcntl is None:
        yield
        return
    fd = os.open(TOKEN_PATH + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _post_token(body_dict):
    body = urllib.parse.urlencode(body_dict).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"Token request failed ({e.code}): {err_body}")


def login(username, password):
    """Initial login via Resource Owner Password Credentials grant.
    Stores tokens; never persists the raw password."""
    data = _post_token({
        "client_id": CLIENT_ID,
        "grant_type": "password",
        "username": username,
        "password": password,
    })
    now = time.time()
    d = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "token_type": data.get("token_type", "Bearer"),
        "access_expires_at": now + data["expires_in"],
        "refresh_expires_at": now + data["refresh_expires_in"],
        "realm": REALM,
        "client_id": CLIENT_ID,
        "token_url": TOKEN_URL,
        "username": username,
    }
    _save(d)
    return d


def _refresh(d):
    data = _post_token({
        "client_id": d.get("client_id", CLIENT_ID),
        "grant_type": "refresh_token",
        "refresh_token": d["refresh_token"],
    })
    now = time.time()
    d["access_token"] = data["access_token"]
    d["refresh_token"] = data.get("refresh_token", d["refresh_token"])  # Keycloak rotates refresh tokens
    d["access_expires_at"] = now + data["expires_in"]
    d["refresh_expires_at"] = now + data.get("refresh_expires_in", d["refresh_expires_at"] - now)
    _save(d)
    return d


def get_access_token():
    try:
        d = _load()
    except FileNotFoundError:
        raise RuntimeError(
            f"No stored tokens at {TOKEN_PATH}. Ask the user to run, in their own terminal:\n"
            "  python3 filterlabs_auth.py --login <email>"
        )
    if d["access_expires_at"] - time.time() > LEEWAY_SECONDS:
        return d["access_token"]
    with _locked():
        d = _load()  # another process may have refreshed while we waited
        now = time.time()
        if d["access_expires_at"] - now > LEEWAY_SECONDS:
            return d["access_token"]
        if d["refresh_expires_at"] - now <= LEEWAY_SECONDS:
            raise RuntimeError(
                "Refresh token has also expired. Ask the user to re-run, in their own terminal:\n"
                "  python3 filterlabs_auth.py --login <email>"
            )
        d = _refresh(d)
        return d["access_token"]


def status():
    d = _load()
    now = time.time()
    return {
        "username": d.get("username"),
        "access_expires_in_s": round(d["access_expires_at"] - now, 1),
        "refresh_expires_in_s": round(d["refresh_expires_at"] - now, 1),
    }


USAGE = """Usage:
  filterlabs_auth.py                               print a valid access token
  filterlabs_auth.py --status                      print expiry info (no token)
  filterlabs_auth.py --login <email> [--password-stdin]
                                                   log in; the password is read from a
                                                   no-echo prompt (or one line of stdin
                                                   with --password-stdin), never argv
  filterlabs_auth.py --help                        show this help"""


def main(argv):
    """CLI entry point. Returns the process exit code.

    The bare invocation is the only path that prints a token (documented
    usage is `T=$(python3 filterlabs_auth.py)`). Everything else, including
    --help and unknown flags, prints usage or status and exits, because the
    old fall-through printed a live token for any argument it did not know."""
    if not argv:
        print(get_access_token())
        return 0
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if argv[0] == "--status" and len(argv) == 1:
        print(json.dumps(status(), indent=2))
        return 0
    if argv[0] == "--login":
        rest = argv[1:]
        stdin_pw = "--password-stdin" in rest
        args = [a for a in rest if a != "--password-stdin"]
        if len(args) != 1 or args[0].startswith("-"):
            print(USAGE + "\n\nThe password is never accepted on the command line.",
                  file=sys.stderr)
            return 1
        email = args[0]
        if stdin_pw:
            password = sys.stdin.readline().rstrip("\n")
        else:
            password = getpass.getpass(f"Password for {email}: ")
        login(email, password)
        del password
        print(f"Login successful. Tokens saved to {TOKEN_PATH}")
        return 0
    print(f"Unknown arguments: {' '.join(argv)}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
