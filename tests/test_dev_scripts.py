"""Offline tests for the skill-dev-workflow scripts: scan_for_leaks.py and
repo_location.py.

Secret-shaped fixtures are assembled from pieces at runtime so that this file
itself does not trip the leak scanner or a host's push protection.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

import _support as h


FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"  # shape only, not a real key


class TestLeakScanner(h.TempDirCase):
    def setUp(self):
        super().setUp()
        self.mod = h.load_script(h.LEAK_PY, "scan_for_leaks_under_test")

    def scan_text(self, text, name="SKILL.md"):
        p = self.home / name
        p.write_text(text)
        return self.mod.scan_file(str(p))

    def kinds(self, text):
        return {f["kind"] for f in self.scan_text(text)}

    def test_detects_core_secret_shapes(self):
        """A single scan must catch all six core secret shapes in one pass:
        JWT/bearer token, AWS access key ID, PEM private-key header, email,
        UUID, and a quoted key=value secret assignment. A regression in any
        one pattern shows up here, not just in its own dedicated test."""
        jwt = ".".join(["eyJ" + "hbGciOiJub25lIn0", "eyJ" + "zdWIiOiJmYWtlLXVzZXIifQ", "ZmFrZS1zaWduYXR1cmU"])
        self.assertIn("jwt_or_bearer_token", self.kinds(f"Authorization: Bearer {jwt}"))
        self.assertIn("aws_access_key_id", self.kinds("key " + FAKE_AWS + " here"))
        self.assertIn("pem_private_key", self.kinds("-----BEGIN " + "RSA PRIVATE KEY-----"))
        self.assertIn("email", self.kinds("contact real.person" + "@company.io"))
        self.assertIn("uuid", self.kinds("id 3f2b8c1e-9a4d-4e2f-8b1a-0c9d8e7f6a5b"))
        self.assertIn("generic_secret_assignment", self.kinds("api_key = " + "'abcd1234efgh5678'"))

    def test_allowlisted_placeholders_ignored(self):
        """A documented placeholder address (user@example.com) must produce
        zero findings -- without this allowlist, every doc example using a
        placeholder would trigger noise on every scan."""
        self.assertEqual(self.scan_text("mail user@example.com"), [])

    def test_cli_exit_codes(self):
        """Runs the script as a real subprocess (not an in-process call) to
        test the actual CLI contract scripts/CI gates rely on: exit 0 on a
        clean file, exit 1 with --json output containing the real finding
        on a dirty file."""
        clean = self.home / "clean.md"
        clean.write_text("nothing to see")
        dirty = self.home / "dirty.md"
        dirty.write_text(FAKE_AWS)
        script = str(h.REPO / h.LEAK_PY)
        ok = subprocess.run([sys.executable, "-I", script, str(clean)], capture_output=True)
        bad = subprocess.run([sys.executable, "-I", script, "--json", str(dirty)],
                             capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)[0]["kind"], "aws_access_key_id")

    def test_flags_bare_token_assignment_documented_in_skill(self):
        """SKILL.md promises `token="..."` assignments are flagged -- tests
        the literal documented contract, not just the pattern in isolation."""
        self.assertIn("generic_secret_assignment",
                      self.kinds("token = " + '"Zx81kQ0pLmN3vB7cR2tY"'))

    def test_flags_json_style_password(self):
        """A captured request body pasted into a SKILL.md looks like JSON, with
        a closing quote between the key and ':'. This is the JSON-body shape
        gap PR #26 specifically closed -- the scanner used to only catch
        code-style `password = "..."`, not `"password": "..."`."""
        self.assertIn("generic_secret_assignment",
                      self.kinds('{"username": "a", "password": ' + '"hunter2hunter2"}'))

    def test_flags_refresh_token_in_json(self):
        """Same JSON-body shape coverage as above, specifically for
        refresh_token -- a value an agent is especially likely to paste
        verbatim from a captured API response while writing docs."""
        self.assertIn("generic_secret_assignment",
                      self.kinds('{"refresh_token": ' + '"8f1c2e9a7b6d5c4e3f2a1b0c"}'))


class TestRepoLocation(h.TempDirCase):
    def setUp(self):
        super().setUp()
        self.mod = h.load_script(h.REPOLOC_PY, "repo_location_under_test")
        self.mod.CONFIG_PATH = str(self.home / ".hermes/state/ubiquity-skills-repo.json")

    def git_repo(self, name, remote):
        d = self.home / name
        d.mkdir()
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        subprocess.run(["git", "-C", str(d), "remote", "add", "origin", remote], check=True)
        return d

    def test_set_then_get_roundtrip(self):
        """`--set` on a real git repo (actual `git init`/`remote add`, not a
        mock) must persist a path that `--get` then returns verbatim."""
        d = self.git_repo("clone", "git@github.com:FilterLabsAI/ubiquity-skills.git")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.mod.cmd_set(str(d)), 0)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.mod.cmd_get(), 0)
        self.assertEqual(out.getvalue().strip(), str(d))

    def test_rejects_non_git_and_wrong_remote(self):
        """Two distinct negative cases must both fail validate(): a plain
        directory with no .git, and a real git repo whose origin remote
        points at a different (but also legitimate-looking) GitHub repo."""
        plain = self.home / "plain"
        plain.mkdir()
        self.assertFalse(self.mod.validate(str(plain))[0])
        other = self.git_repo("other", "https://github.com/someone/else.git")
        self.assertFalse(self.mod.validate(str(other))[0])

    def test_accepts_git_worktree(self):
        """In a `git worktree` (or submodule) `.git` is a file, not a
        directory. Runs a real `git worktree add` (not simulated) and
        checks validate() still passes -- a check that only accepted
        directories would wrongly reject worktree/submodule users."""
        main = self.git_repo("main", "https://github.com/FilterLabsAI/ubiquity-skills.git")
        subprocess.run(["git", "-C", str(main), "-c", "user.email=t@example.com", "-c",
                        "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        wt = self.home / "wt"
        subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(wt)], check=True)
        ok, checks, reason = self.mod.validate(str(wt))
        self.assertTrue(ok, reason)

    def test_rejects_lookalike_remote(self):
        """A remote that merely contains 'FilterLabsAI/ubiquity-skills' on
        another host must not pass. Guards against the exact vulnerability
        class of a substring match: `evil.example.com/x/FilterLabsAI/
        ubiquity-skills-fork.git` contains the right text but is neither
        github.com nor the real repo name."""
        d = self.git_repo("fork", "https://evil.example.com/x/FilterLabsAI/ubiquity-skills-fork.git")
        self.assertFalse(self.mod.validate(str(d))[0])

    def test_accepts_case_variant_of_github_remote(self):
        """GitHub owner/repo names are case-insensitive, so a remote spelled
        `filterlabsai` (lowercase) must still validate."""
        d = self.git_repo("lc", "git@github.com:filterlabsai/ubiquity-skills.git")
        self.assertTrue(self.mod.validate(str(d))[0])

    def test_empty_set_is_an_error(self):
        """Runs the real CLI as a subprocess with `--set ''`; must exit
        non-zero rather than silently "succeeding" at saving nothing."""
        script = str(h.REPO / h.REPOLOC_PY)
        r = subprocess.run([sys.executable, "-I", script, "--set", ""],
                           capture_output=True, text=True,
                           env={**os.environ, "HOME": str(self.home)})
        self.assertNotEqual(r.returncode, 0, "`--set ''` must not exit 0 without saving")


if __name__ == "__main__":
    unittest.main()
