"""Offline tests for skills/ubiquity-entity-review/scripts/entity_review.py.

Run from the repo root:  python3 -m unittest discover -s tests -v

All HTTP goes to FakeUbiquity, a small in-memory model of the endpoints the
script uses (entities list, votes list, vote toggle, entity delete,
evaluation log), with the real toggle semantics: sending the same vote
twice removes it.
"""
import contextlib
import io
import json
import re
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _support as h  # noqa: E402

PIPE = "p-0000"
FEED = 42


class FakeUbiquity:
    """Stateful fake of the entity-review endpoints with real toggle
    semantics (same vote_type twice removes it, per SKILL.md)."""

    def __init__(self, n_entities=10, votes=None, total=None):
        self.entities = [
            {"id": i, "name": f"Entity {i}", "source_count": 1,
             "sources": [{"url_to_scan": f"https://src{i}.example.com"}],
             "metadata": {"type": "institution", "credibility_score": i / 100.0,
                          "language": "en", "local_focus": "high", "quality": "good",
                          "url": f"https://src{i}.example.com"}}
            for i in range(1, n_entities + 1)
        ]
        self.total = total if total is not None else n_entities
        self.votes = list(votes or [])
        self.toggles = []

    def routes(self):
        return [
            ("GET", f"/api/locations/api/v1/feeds/{FEED}/entities", self.list_entities),
            ("GET", f"/api/locations/v1/entity-votes/pipeline/{PIPE}", self.list_votes),
            ("POST", "/api/locations/v1/entity-votes/toggle", self.toggle),
            ("DELETE", f"/api/locations/api/v1/feeds/{FEED}/entities/", self.delete),
            ("GET", "/api/locations/api/v1/source-evaluation-logs/by-url", self.evlog),
        ]

    def list_entities(self, req, body):
        q = dict(p.split("=", 1) for p in req.full_url.split("?", 1)[1].split("&"))
        limit, offset = int(q.get("limit", 100)), int(q.get("offset", 0))
        page = self.entities[offset:offset + limit]
        return 200, {"entities": page, "total": self.total,
                     "source_count": self.total, "dataset_count": 0}

    def list_votes(self, req, body):
        return 200, self.votes

    def toggle(self, req, body):
        self.toggles.append(body)
        key = (body["entity_id"], body["vote_type"])
        for v in self.votes:
            if (v["entity_id"], v["vote_type"]) == key:
                self.votes.remove(v)
                return 200, {"action": "removed", "vote": v}
        v = {"entity_id": body["entity_id"], "vote_type": body["vote_type"]}
        self.votes.append(v)
        return 201, {"action": "created", "vote": v}

    def delete(self, req, body):
        eid = int(req.full_url.rsplit("/", 1)[1])
        self.entities = [e for e in self.entities if e["id"] != eid]
        return 200, {"message": "Entity removed from feed successfully"}

    def evlog(self, req, body):
        return 200, {"evaluation_details": {"evaluation_notes":
                     "Valid source. STRENGTHS: (1) a. LIMITATIONS: (1) b. RECOMMENDED USE: c."}}


class ERBase(h.TempDirCase):
    def setUp(self):
        super().setUp()
        self.mod = h.load_script(h.ER_PY, "entity_review_under_test")
        self.mod.TOKENS_PATH = self.home / ".hermes/secrets/filterlabs_tokens.json"
        self.mod.SESSION_DIR = self.home / ".hermes/cache/entity_review_sessions"
        self.mod.TOKENS_PATH.parent.mkdir(parents=True)
        self.token = h.fake_jwt()
        self.mod.TOKENS_PATH.write_text(json.dumps({
            "access_token": self.token, "refresh_token": "rt",
            "access_expires_at": time.time() + 1800,
            "refresh_expires_at": time.time() + 28800}))

    def run_cli(self, fake, *args):
        srv = h.FakeServer(fake.routes())
        with mock.patch.object(self.mod.request, "urlopen", srv), \
                mock.patch.object(sys, "argv", ["entity_review.py", *map(str, args)]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.mod.main()
        return out.getvalue(), srv

    @staticmethod
    def ids_on_page(text):
        return [int(m) for m in re.findall(r"^\[(\d+)\]", text, re.M)]


class TestPureFunctions(ERBase):
    def test_user_uuid_from_jwt_sub(self):
        self.assertEqual(self.mod._user_uuid(h.fake_jwt(sub="abc")), "abc")

    def test_split_notes_sections(self):
        s = self.mod._split_notes_sections(
            "Good outlet. STRENGTHS: (1) x. LIMITATIONS: (1) y. RECOMMENDED USE: z. ACKNOWLEDGE: w")
        self.assertEqual(s["lede"], "Good outlet.")
        self.assertEqual(s["strengths"], "(1) x")
        self.assertEqual(s["limitations"], "(1) y")
        self.assertEqual(s["recommended_use"], "z")
        self.assertEqual(s["acknowledge"], "w")
        self.assertEqual(self.mod._split_notes_sections(""), {})

    def test_build_review_table_joins_votes(self):
        fake = FakeUbiquity(3, votes=[{"entity_id": 2, "vote_type": "like"},
                                      {"entity_id": 2, "vote_type": "flag"}])
        rows = self.mod.build_review_table(fake.entities, fake.votes)
        self.assertEqual(rows[1]["votes"], ["flag", "like"])
        self.assertEqual(rows[0]["votes"], [])
        self.assertEqual(rows[0]["urls"], ["https://src1.example.com"])

    def test_sort_rows_handles_missing_credibility(self):
        rows = [{"id": 1, "name": "b", "credibility": None},
                {"id": 2, "name": "a", "credibility": 0.5}]
        self.assertEqual([r["id"] for r in self.mod.sort_rows(rows)], [1, 2])
        self.assertEqual([r["id"] for r in self.mod.sort_rows(rows, "name")], [2, 1])

    def test_suggest_flags_disproportionate_dislikes(self):
        rows = [{"votes": ["dislike"], "type": "x", "language": "en", "local_focus": "low",
                 "quality": "fair", "credibility": 0.2} for _ in range(3)]
        rows += [{"votes": ["like"], "type": "x", "language": "en", "local_focus": "high",
                  "quality": "good", "credibility": 0.8}]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.mod.suggest_updates(rows)
        self.assertIn("quality='fair' are disproportionately disliked", out.getvalue())
        self.assertIn("credibility_threshold", out.getvalue())

    def test_suggest_without_votes(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.mod.suggest_updates([{"votes": []}])
        self.assertIn("No votes recorded yet", out.getvalue())


class TestHttp(ERBase):
    def test_call_sets_headers(self):
        fake = FakeUbiquity(1)
        srv = h.FakeServer(fake.routes())
        with mock.patch.object(self.mod.request, "urlopen", srv):
            self.mod.vote(self.token, PIPE, 1, "like")
        c = srv.calls[0]
        self.assertEqual(c["headers"]["authorization"], f"Bearer {self.token}")
        self.assertTrue(c["headers"]["user-agent"].startswith("Mozilla/5.0"))
        self.assertEqual(c["headers"]["content-type"], "application/json")
        self.assertEqual(c["body"]["keycloak_user_id"], "11111111-2222-3333-4444-555555555555")

    def test_http_error_returns_status(self):
        srv = h.FakeServer([("DELETE", "/", lambda r, b: (404, {"error": "nope"}))])
        with mock.patch.object(self.mod.request, "urlopen", srv):
            status, data = self.mod.remove_entity(self.token, FEED, 9)
        self.assertEqual((status, data), (404, {"error": "nope"}))

    def test_apply_drops_successes_and_keeps_failures(self):
        fake = FakeUbiquity(4)
        self.run_cli(fake, "start", "--feed-id", FEED, "--pipeline-id", PIPE)
        self.run_cli(fake, "queue", "--feed-id", FEED, "--pipeline-id", PIPE,
                     "--entity-id", 1, "--vote-type", "like")
        self.run_cli(fake, "queue-remove", "--feed-id", FEED, "--pipeline-id", PIPE,
                     "--entity-id", 99)
        # make the removal fail server-side so it must stay queued
        fake.delete = lambda req, body: (404, {"error": "Entity not found"})
        out, _ = self.run_cli(fake, "apply", "--feed-id", FEED, "--pipeline-id", PIPE)
        sess = json.loads((self.mod.SESSION_DIR / f"{FEED}_{PIPE}.json").read_text())
        self.assertEqual(sess["queued_votes"], {})
        self.assertEqual(sess["queued_removals"], [99])
        self.assertIn("Applied 1/2", out)

    def test_page_with_notes(self):
        fake = FakeUbiquity(3)
        out, srv = self.run_cli(fake, "page", "--feed-id", FEED, "--pipeline-id", PIPE,
                                "--page", 0, "--page-size", 2)
        self.assertIn("VERDICT:   Valid source.", out)
        self.assertEqual(sum(1 for c in srv.calls if "evaluation-logs" in c["path"]), 2)


class TestReviewSafety(ERBase):
    def test_queued_votes_do_not_shift_pages_with_only_unvoted(self):
        """SKILL.md: `start` + `queue` 'guarantees page numbers stay stable even
        with --only-unvoted active'. The script used to mark queued entities as voted
        and then filters them out, so page 1 slides into page 0's slot and the
        reviewer never sees entities 6-10."""
        fake = FakeUbiquity(10)
        self.run_cli(fake, "start", "--feed-id", FEED, "--pipeline-id", PIPE,
                     "--sort-by", "id", "--only-unvoted")
        out0, _ = self.run_cli(fake, "page", "--feed-id", FEED, "--pipeline-id", PIPE,
                               "--page", 0, "--page-size", 5, "--only-unvoted",
                               "--no-with-notes")
        first = self.ids_on_page(out0)
        self.assertEqual(first, [1, 2, 3, 4, 5])
        for eid in first:
            self.run_cli(fake, "queue", "--feed-id", FEED, "--pipeline-id", PIPE,
                         "--entity-id", eid, "--vote-type", "like")
        out1, _ = self.run_cli(fake, "page", "--feed-id", FEED, "--pipeline-id", PIPE,
                               "--page", 1, "--page-size", 5, "--only-unvoted",
                               "--no-with-notes")
        self.assertEqual(self.ids_on_page(out1), [6, 7, 8, 9, 10])

    def test_queued_removal_does_not_shift_pages(self):
        fake = FakeUbiquity(10)
        self.run_cli(fake, "start", "--feed-id", FEED, "--pipeline-id", PIPE, "--sort-by", "id")
        self.run_cli(fake, "queue-remove", "--feed-id", FEED, "--pipeline-id", PIPE,
                     "--entity-id", 2)
        out1, _ = self.run_cli(fake, "page", "--feed-id", FEED, "--pipeline-id", PIPE,
                               "--page", 1, "--page-size", 5, "--no-with-notes")
        self.assertEqual(self.ids_on_page(out1), [6, 7, 8, 9, 10])

    def test_apply_does_not_toggle_off_an_existing_vote(self):
        """The vote endpoint is a toggle. Queueing 'like' on an entity that
        already has a live 'like' (liked in the UI, or by an earlier ad-hoc
        `vote`) used to make `apply` silently REMOVE the like and report OK."""
        fake = FakeUbiquity(3, votes=[{"entity_id": 2, "vote_type": "like"}])
        self.run_cli(fake, "start", "--feed-id", FEED, "--pipeline-id", PIPE)
        self.run_cli(fake, "queue", "--feed-id", FEED, "--pipeline-id", PIPE,
                     "--entity-id", 2, "--vote-type", "like")
        self.run_cli(fake, "apply", "--feed-id", FEED, "--pipeline-id", PIPE)
        self.assertIn({"entity_id": 2, "vote_type": "like"}, fake.votes,
                      "apply removed the user's existing like")

    def test_fetch_entities_reads_every_page(self):
        """fetch_entities used to ask for limit=500 once and never page, so a
        bigger feed was silently truncated in list/page/start/suggest."""
        fake = FakeUbiquity(620)
        srv = h.FakeServer(fake.routes())
        with mock.patch.object(self.mod.request, "urlopen", srv):
            ents, total, *_ = self.mod.fetch_entities(self.token, FEED)
        self.assertEqual(len(ents), total)

    def test_http_calls_have_a_timeout(self):
        fake = FakeUbiquity(1)
        srv = h.FakeServer(fake.routes())
        with mock.patch.object(self.mod.request, "urlopen", srv):
            self.mod.fetch_votes(self.token, PIPE)
        self.assertIsNotNone(srv.calls[0]["timeout"], "urlopen called without timeout")

    def test_expired_access_token_is_refreshed_before_use(self):
        """Review sessions outlast the 30-minute access token. The script used
        to send the stored token without checking its expiry, so calls began
        failing with 401 midway through a review. It now goes through
        ubiquity-auth's get_access_token, which refreshes first."""
        data = json.loads(self.mod.TOKENS_PATH.read_text())
        data["access_expires_at"] = time.time() - 60
        self.mod.TOKENS_PATH.write_text(json.dumps(data))
        fresh = h.fake_jwt() + ".fresh"
        srv = h.FakeServer([("POST", "/realms/", lambda r, b: (200, {
            "access_token": fresh, "refresh_token": "rt-2", "token_type": "Bearer",
            "expires_in": 1800, "refresh_expires_in": 28800}))])
        with mock.patch("urllib.request.urlopen", srv):
            tok = self.mod._load_token()
        self.assertEqual(tok, fresh)
        self.assertIn("grant_type=refresh_token", srv.calls[0]["body"])

    def test_queue_works_without_a_token_file(self):
        """queue / queue-remove only edit the local session file, so they
        must not need (or crash without) the token file."""
        fake = FakeUbiquity(3)
        self.run_cli(fake, "start", "--feed-id", FEED, "--pipeline-id", PIPE)
        self.mod.TOKENS_PATH.unlink()
        try:
            self.run_cli(fake, "queue", "--feed-id", FEED, "--pipeline-id", PIPE,
                         "--entity-id", 1, "--vote-type", "like")
        except FileNotFoundError as e:
            self.fail(f"queue needed the token file: {e}")


if __name__ == "__main__":
    unittest.main()
