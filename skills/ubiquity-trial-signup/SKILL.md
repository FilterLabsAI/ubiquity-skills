---
name: ubiquity-trial-signup
description: Use to create new Ubiquity trial accounts for agents.
---

# Ubiquity: creating a new trial account ("Ubiquity for Agents" preview)

Covers the self-serve signup flow at `https://agents.ubiquity.filterlabs.ai`
-- a separate, minimal site distinct from the main `ubiquity.filterlabs.ai`
product, purpose-built for provisioning a new account non-interactively
(no password typed anywhere in the flow until the user clicks an emailed
link). Useful when a new agent/account needs its own Ubiquity login
rather than reusing an existing one. See `ubiquity-auth` for logging in
once the account exists.

## The flow -- CONFIRMED on the wire
The signup page is a single form: **Email** (required), **First name**
(optional), **Last name** (optional), and a "Create account" button.
Submitting calls:
```
POST https://agents.ubiquity.filterlabs.ai/api/v1/signup
Content-Type: application/json
{"email": "<email>", "first_name": "<optional>", "last_name": "<optional>"}
```
**Confirmed: `first_name`/`last_name` are omitted from the request body
entirely when left blank** (not sent as empty strings) -- email alone is
a fully valid payload. Response (confirmed live, `200`):
```json
{"user_id": "<uuid>", "email": "<email>", "created": true, "licensed": true, "invited": true}
```
`created`/`licensed`/`invited` are all `true` on a genuinely new signup.
The UI then shows: *"You're in. We sent a password link to `<email>`.
Set your password, then install the Ubiquity skills for your agents.
(https://github.com/FilterLabsAI/ubiquity-skills)."* -- the preview
site's own success message points at this same skills repo.

**No email deliverability or domain-existence check is performed
server-side.** Confirmed: a syntactically valid but undeliverable
address (an obviously fake `@nonexistent-domain-xyz123.invalid` test
email) got `created: true, licensed: true, invited: true` identically
to a real address -- the backend will happily create a licensed
account for an email it can never actually reach. The ONLY validation observed is the browser's
own HTML5 `type="email"` client-side check on the input (a malformed
string like `not-a-valid-email` never even reaches the API -- the
browser blocks the request before it fires). If scripting this directly
(bypassing the browser form), there is no equivalent of that client-side
check -- the server accepts any syntactically-plausible email with no
feedback either way, so double-check the address is correct before
submitting.

## Re-signup with an existing email -- CONFIRMED idempotent, does not resend
Submitting the SAME email again returns `200` with the SAME `user_id`,
but `created: false, invited: false` (`licensed` stays `true`) -- it
does NOT create a duplicate account or re-send the invite email. The UI
shows a different message in this case: *"`<email>` already has access.
Check your email for the password link."* Use this response's
`created`/`invited` fields to distinguish a brand-new signup from a
repeat hit on an already-provisioned email, e.g. if scripting bulk
account creation and re-running is possible.

## The password-setup email -- CONFIRMED live
Sent from `Ubiquity <no-reply@filterlabs.ai>` (reply-to
`support@filterlabs.ai`), subject "Finish setting up your Ubiquity
account", via Amazon SES. It contains a single link of the form:
```
https://auth.filterlabs.ai/realms/filter-labs-web/login-actions/action-token?key=<JWT>
```
This is the SAME Keycloak instance/realm (`filter-labs-web`) documented
in `ubiquity-auth` -- the signup flow provisions a real Keycloak user,
not a separate account system. Decoding the `key` JWT (HS512, not
verifiable client-side without the signing secret, but readable):
```json
{
  "exp": "<issued + 3 days>", "iat": "<issue time>",
  "iss": "https://auth.filterlabs.ai/realms/filter-labs-web",
  "sub": "<the same user_id from the signup response>",
  "typ": "execute-actions", "azp": "web-app",
  "eml": "<the signup email>",
  "rqac": ["UPDATE_PASSWORD", "VERIFY_EMAIL"],
  "reduri": "https://ubiquity.filterlabs.ai/"
}
```
**Confirmed: the link expires in exactly 3 days** (`exp - iat =
259200s`), after which a fresh signup submission (same or different
email) would be needed to get a new link -- re-submitting the SAME
email per the idempotent behavior above does NOT appear to issue a new
link (not independently re-tested after expiry, but the unchanged
`invited: false` on a repeat submission strongly suggests it reuses
whatever invite state already exists rather than minting a new token).
Opening the link runs Keycloak's own required-actions flow (set
password + verify email in one step), then redirects to
`https://ubiquity.filterlabs.ai/` already logged in.

## Practical use for Hermes
- To provision a new Ubiquity account programmatically (e.g. for a new
  user, a new agent identity, or a disposable test account), POST to
  `/api/v1/signup` directly -- no browser needed for this step, it's a
  plain unauthenticated REST call (no Bearer token required, this is
  the one Ubiquity-adjacent endpoint that predates having any account).
- The actual password-setting step CANNOT be scripted/automated by
  Hermes -- it's a Keycloak-hosted form behind an emailed link, and per
  `ubiquity-auth`'s absolute rule, a password must never be typed by the
  agent. The user (or whoever owns the target inbox) must click the
  link and set their own password; only then does `ubiquity-auth`'s
  `--login` become usable for that account.
- After signup, direct the user to this skill family
  (`ubiquity-skills` on GitHub, same repo this skill lives in) to wire
  up their agent's access, per the signup page's own closing message.

## Pitfalls
- Don't confuse `agents.ubiquity.filterlabs.ai` (this signup-only
  preview site) with `ubiquity.filterlabs.ai` (the actual product) or
  `auth.filterlabs.ai` (the Keycloak instance both sites share) -- three
  distinct hostnames, one shared backend identity system.
- `/health` on the signup site (confirmed live, no auth needed) reports
  on the underlying service as `"service": "ubiquity-scout"` -- the
  signup API is hosted alongside/as part of the Scout search service,
  not a standalone signup microservice; useful to know if debugging
  availability.
- The success/duplicate UI messages are the only user-facing feedback;
  there is no account-management UI on this preview site itself (no
  password reset, no resend-invite button) -- those live in the main
  product or Keycloak's own flows, not here.
