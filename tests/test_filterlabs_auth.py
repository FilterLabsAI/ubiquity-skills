"""Offline tests for skills/ubiquity-auth/scripts/filterlabs_auth.py.

No network: _support disables sockets and every HTTP call goes to a fake
Keycloak token endpoint. Each test points TOKEN_PATH into a temp dir.
"""
import contextlib
import io
import json
import os
import stat
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import _support as h

TOKEN_URL = "/realms/filter-labs-web/protocol/openid-connect/token"


def token_payload(i=1):
    return {"access_token": h.fake_jwt() + f".a{i}", "refresh_token": f"rt-{i}",
            "token_type": "Bearer", "expires_in": 1800, "refresh_expires_in": 28800}


class AuthBase(h.TempDirCase):
    def setUp(self):
        super().setUp()
        self.mod = h.load_script(h.AUTH_PY, "filterlabs_auth_under_test")
        self.mod.TOKEN_PATH = str(self.home / ".hermes/secrets/filterlabs_tokens.json")

    def write_tokens(self, access_in=1800, refresh_in=28800, rt="rt-0", at="cached-at"):
        os.makedirs(os.path.dirname(self.mod.TOKEN_PATH), exist_ok=True)
        now = time.time()
        with open(self.mod.TOKEN_PATH, "w") as f:
            json.dump({"access_token": at, "refresh_token": rt,
                       "access_expires_at": now + access_in,
                       "refresh_expires_at": now + refresh_in,
                       "client_id": "web-app"}, f)

    def run_cli(self, argv, stdin=""):
        """Run main(argv); return (exit_code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("sys.stdin", io.StringIO(stdin)):
            code = self.mod.main(argv)
        return code, out.getvalue(), err.getvalue()


class TestLoginAndRefresh(AuthBase):
    def test_login_uses_password_grant_and_never_stores_password(self):
        """login() must POST grant_type=password with the real client_id, and
        the raw password must never land in the token file on disk (which
        must be created 0600, not world/group readable)."""
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload()))])
        with mock.patch("urllib.request.urlopen", srv):
            self.mod.login("tester@example.com", "s3cret-pw")
        body = srv.calls[0]["body"]
        self.assertIn("grant_type=password", body)
        self.assertIn("client_id=web-app", body)
        self.assertNotIn("s3cret-pw", Path(self.mod.TOKEN_PATH).read_text())
        self.assertEqual(stat.S_IMODE(os.stat(self.mod.TOKEN_PATH).st_mode), 0o600)

    def test_request_sets_browser_user_agent_and_timeout(self):
        """Every outgoing token request must carry a browser-like User-Agent
        (the API's WAF 403s on anything else) and a request timeout (urllib
        has no default timeout and would otherwise block forever)."""
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload()))])
        with mock.patch("urllib.request.urlopen", srv):
            self.mod.login("tester@example.com", "pw")
        self.assertTrue(srv.calls[0]["headers"]["user-agent"].startswith("Mozilla/5.0"))
        self.assertIsNotNone(srv.calls[0]["timeout"])

    def test_cached_token_returned_without_http(self):
        """A still-valid cached access token must be returned straight from
        disk with zero HTTP calls -- get_access_token() must not refresh
        just because it was called."""
        self.write_tokens(access_in=1000)
        srv = h.FakeServer([])
        with mock.patch("urllib.request.urlopen", srv):
            self.assertEqual(self.mod.get_access_token(), "cached-at")
        self.assertEqual(srv.calls, [])

    def test_refresh_inside_leeway_rotates_refresh_token(self):
        """Inside the 120s leeway, get_access_token() must actually refresh
        (grant_type=refresh_token) and persist Keycloak's NEW rotated
        refresh_token -- saving the old one would break the next refresh."""
        self.write_tokens(access_in=60)
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload(7)))])
        with mock.patch("urllib.request.urlopen", srv):
            tok = self.mod.get_access_token()
        self.assertTrue(tok.endswith(".a7"))
        self.assertIn("grant_type=refresh_token", srv.calls[0]["body"])
        self.assertEqual(json.loads(Path(self.mod.TOKEN_PATH).read_text())["refresh_token"], "rt-7")

    def test_expired_refresh_token_raises_without_http(self):
        """A refresh token that has also expired must raise a RuntimeError
        telling the user to re-run --login, and must not attempt any HTTP
        call (it would fail anyway, but should fail fast locally)."""
        self.write_tokens(access_in=-10, refresh_in=30)
        srv = h.FakeServer([])
        with mock.patch("urllib.request.urlopen", srv):
            with self.assertRaises(RuntimeError) as cm:
                self.mod.get_access_token()
        self.assertEqual(srv.calls, [])
        self.assertIn("--login <email>", str(cm.exception))

    def test_http_error_becomes_runtime_error(self):
        """A Keycloak HTTP error (e.g. 401 on bad credentials) must surface
        as a RuntimeError with the status code in the message, not an
        unhandled urllib.error.HTTPError leaking a raw stack trace."""
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (401, {"error": "invalid_grant"}))])
        with mock.patch("urllib.request.urlopen", srv):
            with self.assertRaises(RuntimeError) as cm:
                self.mod.login("tester@example.com", "bad")
        self.assertIn("401", str(cm.exception))

    def test_missing_token_file_gives_login_hint(self):
        """No token file at all (first-ever run) must raise a RuntimeError
        pointing at --login, not crash with a raw FileNotFoundError."""
        with self.assertRaises(RuntimeError) as cm:
            self.mod.get_access_token()
        self.assertIn("--login", str(cm.exception))


class TestPasswordHandling(AuthBase):
    def test_login_prompts_for_password_instead_of_taking_it_from_argv(self):
        """`--login email` with no password arg must prompt via getpass (no
        echo) and never print the typed password back to stdout."""
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload()))])
        with mock.patch("urllib.request.urlopen", srv), \
                mock.patch("getpass.getpass", return_value="from-getpass"):
            code, out, _ = self.run_cli(["--login", "tester@example.com"])
        self.assertEqual(code, 0)
        self.assertIn("password=from-getpass", srv.calls[0]["body"])
        self.assertNotIn("from-getpass", out)

    def test_login_reads_password_from_stdin_when_asked(self):
        """`--password-stdin` must read the password from one piped stdin
        line and must NOT call getpass (mocked to raise if invoked, so a
        regression that still prompts fails loudly)."""
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload()))])
        with mock.patch("urllib.request.urlopen", srv), \
                mock.patch("getpass.getpass", side_effect=AssertionError("should not prompt")):
            code, _, _ = self.run_cli(["--login", "tester@example.com", "--password-stdin"],
                                      stdin="piped-pw\n")
        self.assertEqual(code, 0)
        self.assertIn("password=piped-pw", srv.calls[0]["body"])

    def test_password_given_as_argument_is_refused(self):
        """A password passed as a 3rd positional CLI arg must be rejected
        (non-zero exit, zero HTTP calls, explanatory stderr) -- this is the
        exact vulnerability class the rewrite targets: a password on argv
        is visible via `ps`, /proc/<pid>/cmdline, and shell history."""
        srv = h.FakeServer([])
        with mock.patch("urllib.request.urlopen", srv):
            code, _, err = self.run_cli(["--login", "tester@example.com", "pw-in-argv"])
        self.assertNotEqual(code, 0)
        self.assertEqual(srv.calls, [])
        self.assertIn("never accepted on the command line", err)


class TestCliNeverLeaksToken(AuthBase):
    def test_help_prints_usage_and_no_token(self):
        """`--help`/`-h` must print usage text and must never leak the real
        token on disk -- the old fall-through printed a live token for any
        argument it didn't recognize; this seeds a real token value and
        checks it never appears in --help's output."""
        self.write_tokens(at="LIVE-TOKEN-VALUE")
        for flag in ("--help", "-h"):
            code, out, err = self.run_cli([flag])
            self.assertEqual(code, 0)
            self.assertIn("Usage", out)
            self.assertNotIn("LIVE-TOKEN-VALUE", out + err)

    def test_unknown_argument_exits_2_without_token(self):
        """An unrecognized flag must exit 2 with usage on stderr and never
        print the real on-disk token -- same leak class as --help above,
        exercised via a flag the CLI has never heard of."""
        self.write_tokens(at="LIVE-TOKEN-VALUE")
        code, out, err = self.run_cli(["--token-info"])
        self.assertEqual(code, 2)
        self.assertIn("Usage", err)
        self.assertNotIn("LIVE-TOKEN-VALUE", out + err)

    def test_status_shows_countdowns_only(self):
        """`--status` must print expiry countdowns (access_expires_in_s) but
        must never embed the real on-disk token string."""
        self.write_tokens(at="LIVE-TOKEN-VALUE")
        code, out, _ = self.run_cli(["--status"])
        self.assertEqual(code, 0)
        self.assertIn("access_expires_in_s", out)
        self.assertNotIn("LIVE-TOKEN-VALUE", out)

    def test_bare_invocation_still_prints_token(self):
        """Documented usage `T=$(python3 filterlabs_auth.py)` must keep working.
        This is the control case for the leak tests above: proves the script
        DOES print the token on the one invocation it's supposed to, so
        "never leaks" elsewhere is a real distinction, not vacuous silence."""
        self.write_tokens(at="LIVE-TOKEN-VALUE")
        code, out, _ = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "LIVE-TOKEN-VALUE")


class TestTokenFileSafety(AuthBase):
    def test_token_file_is_never_group_or_world_readable(self):
        """The old code created the file with the umask (0644) and chmod-ed
        afterwards, leaving a window where other users could read it. This
        spies on os.chmod to capture the file's permission bits at the
        moment of creation, before any later chmod call -- a pure
        before/after check on the final mode would miss that window."""
        seen = {}
        real_chmod = os.chmod

        def spy_chmod(p, mode, *a, **k):
            if str(p) == self.mod.TOKEN_PATH:
                seen["mode_before_chmod"] = stat.S_IMODE(os.stat(p).st_mode)
            return real_chmod(p, mode, *a, **k)

        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload()))])
        with mock.patch("urllib.request.urlopen", srv), mock.patch("os.chmod", spy_chmod):
            self.mod.login("tester@example.com", "pw")
        mode = seen.get("mode_before_chmod", stat.S_IMODE(os.stat(self.mod.TOKEN_PATH).st_mode))
        self.assertEqual(mode & 0o077, 0, f"token file existed with mode {oct(mode)}")

    def test_secrets_directory_is_private(self):
        """The secrets/ directory itself must be 0700 -- a private token
        file inside a world-traversable directory is still a leak on
        systems where directory execute permission lets others stat/open
        known filenames inside it."""
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload()))])
        with mock.patch("urllib.request.urlopen", srv):
            self.mod.login("tester@example.com", "pw")
        d = os.path.dirname(self.mod.TOKEN_PATH)
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode) & 0o077, 0)

    def test_failed_write_keeps_previous_tokens(self):
        """A crash mid-write must not truncate the live file and log the user
        out. Injects OSError into json.dump itself (after the atomic temp
        file exists but before it's complete) and checks the ORIGINAL
        tokens are still readable afterward, with no leftover .tmp file."""
        self.write_tokens(access_in=60, rt="rt-good")
        srv = h.FakeServer([("POST", TOKEN_URL, lambda r, b: (200, token_payload(2)))])
        with mock.patch("urllib.request.urlopen", srv), \
                mock.patch("json.dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.mod.get_access_token()
        self.assertEqual(json.loads(Path(self.mod.TOKEN_PATH).read_text())["refresh_token"], "rt-good")
        leftovers = [p for p in os.listdir(os.path.dirname(self.mod.TOKEN_PATH)) if p.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_concurrent_refresh_is_safe(self):
        """Keycloak rotates refresh tokens: two callers refreshing at once with
        the same old token used to make the second fail with invalid_grant.
        Runs two real threads against a fake server that actually enforces
        single-use refresh tokens, and asserts no errors AND exactly one
        real refresh happened (the second thread must see the first
        thread's fresh token via the lock, not race the network)."""
        self.write_tokens(access_in=60, rt="rt-0")
        state = {"valid": "rt-0", "n": 0}
        lock = threading.Lock()

        def handler(req, body):
            time.sleep(0.2)
            with lock:
                if f"refresh_token={state['valid']}" not in body:
                    return 400, {"error": "invalid_grant"}
                state["n"] += 1
                state["valid"] = f"rt-{state['n']}"
                p = token_payload(state["n"])
                p["refresh_token"] = state["valid"]
                return 200, p

        srv = h.FakeServer([("POST", TOKEN_URL, handler)])
        errors = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            try:
                self.mod.get_access_token()
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        with mock.patch("urllib.request.urlopen", srv):
            ts = [threading.Thread(target=worker) for _ in range(2)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(errors, [])
        self.assertEqual(state["n"], 1, "both callers refreshed; expected one refresh")


if __name__ == "__main__":
    unittest.main()
