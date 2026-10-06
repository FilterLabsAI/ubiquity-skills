---
name: ubiquity-skill-dev-workflow
description: Use before committing ubiquity-* skill changes to GitHub.
---

# Reviewing & committing changes to ubiquity-* skills

This skill governs how changes made to any `ubiquity-*` skill (or its
supporting scripts/scratch artifacts intended for commit) get reviewed
and pushed to the team's GitHub mirror repo:
**https://github.com/FilterLabsAI/ubiquity-skills** (private).

**The local clone's path is NOT hardcoded** -- it's resolved once per
machine via `scripts/repo_location.py` (see "Step -1" below) so the
clone can live anywhere the user wants and can be moved later without
editing this skill. Everywhere this doc says `<REPO>` below, that means
"the path `scripts/repo_location.py --get` prints" -- resolve it fresh
at the start of a session rather than assuming a remembered value is
still correct, since the user can move the clone between sessions.

**Never start editing/improving a `ubiquity-*` skill without first
running step 0 (sync the repo + local branch with `main`), and never run
step 2 (the git workflow) without first running step 1 (the leak
scanner) AND step 1.5 (the logical-soundness review) on every file that
will be committed.** This repo and these skills are developed
against a real production account
(see redacted as `<ACCOUNT_EMAIL>` in examples below) against real
pipelines, feeds, entities, and jobs -- it is very easy for a real UUID,
email, token, or internal hostname to end up pasted into a SKILL.md
"confirmed via wire capture" note during development. Treat every commit
as a potential leak vector.

## Step -1: resolve where the repo clone actually lives
Before anything else (including Step 0), find `<REPO>` -- the local
path to the ubiquity-skills clone -- with:
```
python3 scripts/repo_location.py --get
```
This prints the configured path and exits 0 only if that path still
exists, is a git repo, and its `origin` remote actually points at
`FilterLabsAI/ubiquity-skills` (catches a stale config left over from a
moved/deleted/renamed clone). If it exits 1 (nothing configured yet, or
the configured path no longer checks out), ask the user via `clarify`
for the absolute path to their clone:
- If they already have one, save it:
  ```
  python3 scripts/repo_location.py --set /absolute/path/to/their/clone
  ```
  (also re-run `--set` any time the user says they've moved the repo --
  there's no automatic move-detection, just re-pointing).
- If they don't have one yet, offer to create it for them (ask where
  they want it, default to something like `~/filterlabs/ubiquity-skills`
  only as a suggestion, not an assumption):
  ```
  git clone git@github.com:FilterLabsAI/ubiquity-skills.git /chosen/path
  python3 scripts/repo_location.py --set /chosen/path
  ```
`python3 scripts/repo_location.py --status` dumps the full diagnostic
(configured path, each check, and why it failed) if `--get` is failing
and it's unclear why. Use `<REPO>` as a stand-in for "whatever `--get`
just printed" throughout the rest of this skill -- do not hardcode a
path or remember one from an earlier session without re-resolving it.

## Step 0: sync repo + local with `main` before touching anything
Before improving/editing ANY `ubiquity-*` skill content (not just before
the final commit in Step 2), make sure both the local git clone (at
`<REPO>`, resolved in Step -1) and its working branch are caught up
with `origin/main`. Skills get edited live in the Hermes skills
directory via `skill_manage`, but the git clone is the source of truth
for "what does main actually look like right now" -- editing against a
stale clone risks silently redoing work already merged, or missing a
teammate's change to the same file.

```
cd <REPO>
git fetch origin
git status            # must be clean before pulling/merging -- if dirty, stop and ask the user what to do with the local changes first
```

Then branch on what you find:
- **On `main`:** `git pull --ff-only`. If this fails (local main has
  diverged, e.g. someone committed directly), stop and show the user
  `git log --oneline main..origin/main` / `origin/main..main` and ask
  how to reconcile -- do not force-push or force-reset without explicit
  instruction.
- **On an existing feature/ongoing-project branch:** assume it may be
  behind `main` and needs to be caught up before you add more changes.
  Ask the user whether they want `merge` or `rebase` (default to
  `merge` -- safer for a shared/pushed branch, doesn't rewrite commits
  already pushed to `origin`):
  ```
  git merge origin/main        # or: git rebase origin/main
  ```
  - **If this reports conflicts:** STOP. Do not resolve them yourself.
    List the conflicted files (`git status`) and hand it to the user to
    resolve interactively in their own editor/terminal -- conflict
    resolution requires judgment about intent that you don't have
    visibility into. Wait for them to confirm the merge/rebase is
    complete (`git status` clean, no `U` entries) before continuing.
  - **If it's clean:** report what came in from `main` (e.g.
    `git log --oneline HEAD@{1}..HEAD`) so the user knows what they're
    now building on top of.
- **Starting a brand-new branch for this session's work:** just ensure
  `main` itself is up to date first (per the "On `main`" bullet above),
  then branch from it as usual in Step 2.

Only once the clone and current branch are confirmed in sync with
`origin/main` (or the user has explicitly resolved/accepted any
divergence) should you proceed to actually edit skill content.

## Step 1: scan for leaks
Run the scanner against every file you're about to commit:
```
python3 scripts/scan_for_leaks.py <file_or_dir> [<file_or_dir> ...]
```
It flags, with file:line and the matched snippet:
- email addresses (e.g. `<ACCOUNT_EMAIL>`)
- UUIDs (v1-v5, lowercase/uppercase/mixed) -- pipeline IDs, feed IDs,
  entity IDs, location IDs, job IDs are ALL UUIDs in this system and are
  environment-specific; they should not be hardcoded into shared docs
- bearer tokens / JWTs (three base64url segments joined by `.`, or
  `Bearer <token>` strings)
- generic API-key/secret/password/token assignments
  (`password=`, `api_key:`, `secret =`, `token="..."`, etc.)
- AWS-style access key IDs (`AKIA[0-9A-Z]{16}`)
- PEM private key blocks (`-----BEGIN ... PRIVATE KEY-----`)
- bare IPv4 addresses and internal-looking hostnames
  (`*.filterlabs.ai`, `*.internal`, etc.) -- lower severity, still flagged

For EACH finding, present it to the user as a numbered list:
```
#  file:line          kind         snippet                         suggested fix
1  SKILL.md:42        email        <ACCOUNT_EMAIL>                 replace with <REDACTED_EMAIL> or a generic placeholder like user@example.com
2  SKILL.md:88        uuid         <SOME_UUID>                     replace with <PIPELINE_UUID> / <FEED_ID> placeholder, or remove the example entirely if it doesn't add teaching value
3  scripts/foo.py:12  token        Bearer eyJhbGciOi...            MUST be removed/redacted -- never commit a live token even if expired
```
Then ask the user, per finding (or in one batch), to choose:
- **Redact in place** (I do it, using a clearly-fake placeholder, e.g.
  `<PIPELINE_UUID>`, `user@example.com`, `<REDACTED_TOKEN>`) -- the
  default/safe choice for anything that doesn't change the teaching value
  of the example;
- **Keep as-is** -- only for things the user explicitly confirms are
  fine to publish (e.g. a UUID that's actually a public, non-sensitive
  test fixture id, or this repo being private and the ID being low-risk);
- **Remove the whole example/line** -- when redaction would make the
  surrounding text confusing or incomplete.
Re-run the scanner after redacting until it comes back clean (or every
remaining finding has been explicitly accepted by the user). Do NOT
proceed to Step 2 with unresolved findings the user hasn't explicitly
accepted.

## Step 1.5: review for overconfident/underspecified claims (logical soundness pass)
Leak-scanning (Step 1) only catches sensitive DATA, not shaky REASONING --
run a separate pass over the diff for claims that are stated more
confidently than the evidence actually supports. This is a distinct
failure mode from a leak: nothing sensitive is exposed, but a reader will
trust a "CONFIRMED" claim at face value, so overclaiming here is its own
kind of damage. Patterns worth a second look, found repeatedly in
practice:
- A causal/mechanistic explanation inferred from ONE observation and
  stated as fact (e.g. "the API fills slots most-recent-first" from a
  single skewed sample, when "the underlying data is genuinely skewed
  recent" is an equally plausible, untested alternative explanation).
- A rule generalized from only 1-2 examples, especially when those
  examples share a confound (e.g. both test inputs for a slugging rule
  happened to contain a bracketed placeholder -- the rule may only hold
  for that confound, not in general).
- An asymmetric recommendation (e.g. "pad X but not Y") justified by
  appeal to an unrelated phenomenon rather than by actually testing the
  symmetric case.
- A workaround presented as "the fix" when it was never bisected --
  e.g. three DOM events fired together to unstick a stuck form; it's
  unconfirmed whether all three were actually necessary, or merely a
  fix that happens to work. Worth asking: is there a cleaner mechanism
  (direct REST on the resource, a different endpoint) that would make
  the whole workaround moot, rather than just hardening the workaround?
- Two statements in the same section that look contradictory on a quick
  read because they describe different cases (e.g. unfiltered vs.
  filtered request) without an explicit transition sentence connecting
  them -- technically correct but needs a rewrite for clarity, not a
  factual fix.

**Workflow**: list each finding with a one-line description of what's
underspecified, and present them to the user via `clarify` (one question
per finding, each with choices like "soften the wording" / "keep as
stated" / "I have more info, let me explain" / "test it live before
deciding"). Do NOT just soften everything by default -- several findings
in practice turned out to have a correct, more specific answer the user
already knew (e.g. the real sampling semantics of a capped endpoint, or
the actual rolling-average window used downstream) that a reflexive
hedge would have missed. When the user's answer implies a new live test
is actually easy to run (e.g. "let's investigate the REST API directly
rather than reasoning about the DOM workaround"), run it before writing
anything down -- a live-confirmed correction belongs in the skill with
the same "CONFIRMED" weight as anything else, not as a hedge. Only after
every finding has either been fixed, re-verified, or explicitly accepted
by the user as-is should you move on to re-running the leak scanner
(sensitive data can get pulled in incidentally while adding corrective
detail -- e.g. a fresh live-test response) and then Step 2.

## Step 2: branch -> review -> commit -> push -> PR
All of the following happens in `<REPO>` (resolved in Step -1 -- the git
clone of the GitHub mirror -- NOT the live Hermes skills directory at
`~/.hermes/profiles/<profile>/skills/ubiquity/`, which is where you
actually edit skills day to day with `skill_manage`). Before this step,
sync any skill files that changed from the live Hermes skills directory
into this repo clone (copy the changed `SKILL.md`/supporting files over).

1. **Scan + review** (Steps 1 and 1.5 above) -- must be clean/accepted
   before continuing.
2. **Ask the user for a branch name.** Suggest one derived from the
   change (e.g. `docs/multi-location-limit-notes`) but let them override.
   Create it off latest `main`:
   ```
   cd <REPO>
   git checkout main && git pull --ff-only
   git checkout -b <branch-name>
   ```
3. **Copy in the changed skill files**, then show the user the diff
   (`git diff` / `git status`) and ask them to **approve or reject** it
   before committing. If rejected, stop and ask what to change; do not
   commit partial/rejected changes.
4. **Commit with a summary.** Write a commit message that describes WHAT
   changed and WHY in plain terms (not "update SKILL.md") -- e.g.:
   ```
   git add -A
   git commit -m "Document 19-location multi-location persistence limit

   - pipeline-creation: added hard-limit note + 10%-of-max_queries
     threshold for when to split into multiple pipelines instead
   - pipeline-routing: cross-referenced the same guidance"
   ```
5. **Ask the user whether to push** the new branch to `origin`. If yes:
   ```
   git push -u origin <branch-name>
   ```
6. **Ask the user whether to open a pull request.** If yes, create it
   with a description summarizing the change (reuse the commit message
   body) and base `main`:
   ```
   gh pr create --base main --head <branch-name> \
     --title "<short title>" --body "<summary>"
   ```
   Report back the PR URL `gh pr create` prints.

Never skip the user-approval gates in steps 3, 5, and 6 -- each is a
separate yes/no decision point, not a single blanket "ok go ahead".

## Notes
- `gh` (GitHub CLI) must be authenticated (`gh auth status`); if not, run
  `gh auth login --hostname github.com --git-protocol ssh --web` and have
  the user approve the device code in their own browser -- never type a
  GitHub password/token into any prompt yourself.
- The live Hermes skill files (edited via `skill_manage`) and this git
  clone are two separate copies on disk -- there is no automatic sync.
  Always copy the current skill content into the clone right before
  Step 2 so the diff reflects the latest edits.
- `<REPO>`'s location is tracked in `~/.hermes/state/ubiquity-skills-repo.json`
  (via `scripts/repo_location.py`) -- a per-machine config file OUTSIDE
  both this skill's directory and the repo itself, so it survives both a
  `skill_manage` update to this skill AND the user moving the repo clone
  to a new path. If the user moves the clone, just re-run `--set` with
  the new path; nothing else in this skill needs to change.
- If the user has a separate scout-staging/prod skill or script mirror
  (see persistent memory for `~/filterlabs/hermes-ubiquity-scout/`),
  that is a DIFFERENT repo/workflow from this one -- don't conflate the
  two unless the user says so.
