# Signing up for Multicloud

> **Availability.** Self-serve signup is not open yet. New-account registration is switched off
> while we finish two remaining safety checks — a negative security test and a working
> verification-email path — so that a new account cannot slip through half-verified. Until it
> opens, accounts are created by hand: write to **support@multicloud.io** and someone will set one
> up for you. Everything else on this page describes the flow as it actually works once signup
> opens: it is built and tested, just not yet reachable from the public signup page.


This page covers the whole lifecycle: creating an account, organizations, invitations, roles, and
minting (creating) and revoking the API keys that authenticate your traffic. If you are here to install the
Advisor, start at [Step 3 of getting-started.md](getting-started.md#step-3--get-a-catalog-key)
or [Step 1 of manual-install.md](manual-install.md#step-1--get-a-catalog-key) — both send
you back here for the account and key steps, then return you to the install.

---

## Accounts

A Multicloud account is a login on our Keycloak identity service — nothing more. Creating one does
not by itself create or join an organization; it just gets you a session.

**Verify your email before doing anything else.** Creating an organization, and seeing which
organizations might already be yours, both require a verified address — an unverified session
can sign in, but sees no organizations and cannot create one. Inviting a colleague and minting a
key aren't checked against your email directly; they're checked against organization ownership,
which you can only reach in practice by first creating an organization — and creating one does
require a verified email. So the effect is the same, even though the check itself is different.

## Organizations

Everything else — API keys, deployments, teammates — belongs to an **organization**, not to you
personally. You can belong to more than one, and your standing differs per organization: owning
one and being an ordinary member of another is normal and expected.

### Creating one

Pick a display name and create the organization. In practice, up to two per day. Two
organizations are allowed to share a display name — the platform assumes some companies run more
than one — so each organization also gets its own unique internal identifier, even
if two people at the same company both type "Acme".

Creating an organization makes you its first member and its first owner.

### Finding an organization that might already be yours

Before you create one, check whether your employer already has one. If Multicloud recognizes
organizations at your email domain, you'll see them listed — **a name and a creation date are all
you are shown** — next to an equally prominent "create a new organization" choice. No members, no
addresses, not even a headcount: this listing cannot tell anyone who works anywhere. (Each row also
carries that organization's internal identifier, which is never displayed; it's only there so the
button described below has a way to say which organization you mean. It names no person.) Free-mail
domains (Gmail, Outlook, iCloud, and similar) are never used for this: two strangers sharing
gmail.com should never be shown to each other.

**This list is a hint, not membership.** Seeing your employer's organization does not add you to
it, and nothing here is ever blocked or admitted automatically — there's no way, at signup time, to
tell an organization that's still active from one somebody abandoned a year ago. If you recognize
one, press **Request to join** on that row. If you don't, or aren't sure, create a new one — that's
the expected path, not a fallback.

### Asking to join one

Pressing **Request to join** does not put you in the organization. It emails that organization's
owners a link. An owner has to open the link, sign in as themselves, and confirm — and only then
does an ordinary invitation, the same one described under "Inviting a colleague" below, arrive in
your inbox. **Nobody is admitted automatically at any point.** The request puts a question in front
of a person; a person's click is the only thing that answers it.

An owner may also simply not act, and that is an ordinary outcome rather than a malfunction. There
is no decline button, and nothing comes back to tell you a request was turned down: the invitation
arriving is the only signal that it worked, and **silence means no.** The link stops working after
seven days, and you're welcome to ask again after that. Pressing the button twice
inside an hour doesn't send a second email, and there's a limit of a handful of requests a day, so
this isn't a way to get someone's attention by volume.

**Creating your own organization stays an equal choice the whole time.** A pending request never
blocks it, never greys it out, and doesn't have to be cancelled first — the two sit side by side on
the page for a reason. If you'd rather not wait on somebody else's inbox, create one and carry on;
you can belong to more than one organization, so an invitation that arrives later costs you
nothing.

### Roles: owners and members

Every organization has members, and a subset of those members are **owners**. Ownership is
per-organization — there is no platform-wide "owner" role. The person who creates an organization
is its first owner; anyone invited afterward joins as an ordinary member, not an owner. There is no
self-serve way to add a second owner today.

Any member of an organization — owner or not — can see who else is in it. Only owners can:

- Invite new members
- Mint, rename, and revoke the organization's catalog API keys

There's no way to remove a member or change anyone's role today, from the account page or the API.

### Inviting a colleague

An owner invites a teammate by email. There's no separate acceptance page to build or maintain —
the invitation is handled by the identity service directly. An invited member is added to the
organization as an ordinary member, **not** as an owner.

---

## API keys

Multicloud issues two different kinds of key, and they are not interchangeable — a catalog key can
never authenticate a deploy request and vice versa, even though both are opaque strings passed in
the same header.

| | Catalog key | Deploy key |
|---|---|---|
| Authenticates | Pricing/catalog queries (e.g. the Advisor) | The Skipper deploy API |
| Who can mint it today | Any owner of the organization, self-serve | A Multicloud operator, on request — not yet self-serve |
| Prefix | `mcc_` | `mck_` |
| Scope | The organization | The organization |

This page covers catalog keys in full, since that's the self-serve path. For deploy keys, ask your
Multicloud contact until deploy keys become self-serve the same way catalog keys are.

### Minting a catalog key

Any owner of an organization can mint a catalog key for it — from the account page, or directly
against the API:

```bash
curl -X POST https://api.multicloud.io/api/v1/api-keys \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"slug": "your-org-slug", "name": "ci-key"}'
```

The response carries the raw key **exactly once**, in a top-level `api_key` field alongside the
key's metadata:

```json
{
  "success": true,
  "data": { "id": "...", "name": "ci-key", "key_prefix": "mcc_a1b2c3d4", "enabled": true, "...": "..." },
  "api_key": "mcc_....",
  "warning": "Store this key now — it is shown once and cannot be retrieved later."
}
```

Copy it now. Only its SHA-256 hash is stored — not us, not support, not a future call to the list
endpoint can produce the raw value again. If it's lost, revoke it and mint a new one; there is no
recovery path, by design.

An organization may hold at most **10 enabled catalog keys** at a time. That caps how many are
*live* at once — it isn't a limit on how many you may ever create — so revoke one you no longer
need before minting another if you reach the limit.

You can tag a key with an `account` label and a free-text `description` — useful for marking which
prospect, environment, or CI pipeline a given key belongs to.

### Listing and renaming

```bash
curl "https://api.multicloud.io/api/v1/api-keys?slug=your-org-slug" -H "Authorization: Bearer $JWT"
```

Any owner sees every catalog key the organization holds — including one minted by a colleague who
has since left. That's deliberate: a key belongs to the organization, not to whoever happened to
create it. The `userid` recorded on a key is an audit trail of who minted it, not a claim of
ownership.

Renaming (`PUT /api/v1/api-keys/{id}`) only changes the label; it doesn't touch the key's value or
its permissions.

### Revoking a key

Self-service, from your account page, or:

```bash
curl -X POST https://api.multicloud.io/api/v1/api-keys/<id>/revoke -H "Authorization: Bearer $JWT"
```

Note that this is a `POST` to a `/revoke` path, not a `DELETE` — the row isn't removed, just
disabled, so the audit trail (who minted it, when it was last used) survives. Any owner of the
organization can revoke any of its keys, again regardless of who minted it. **Revocation takes
effect within a minute, and usually on the very next request.** The API validates keys against a
short-lived in-memory cache, and revoking removes that entry immediately in the process handling the
request. Any other worker process still holding a cached copy re-checks the database within 60 seconds.
So the honest guarantee is at most a minute, not an instant — plan a rotation as "revoke, wait a
minute, confirm", not "revoke and assume".

Revocation checks ownership, not authorship. So the scenario this whole model
exists for is straightforward: an engineer mints a key, then leaves the company. Nobody needs their
old login to shut it off. Any remaining owner revokes it directly.

### Key lifecycle at a glance

| Step | What happens |
|---|---|
| Mint | Any owner requests a key for the organization; the raw value is returned once |
| Store | Only a SHA-256 hash and a non-secret display prefix are kept; the raw value cannot be recovered |
| Use | Sent as `X-API-Key` on catalog requests |
| Rename | Any owner can relabel it; the value and permissions are untouched |
| Revoke | Any owner can revoke it — authorship doesn't matter — and it stops working within a minute, usually on the next request |

---

## Related

- [Advisor: getting started](getting-started.md) — the agent-driven install, which sends
  you here for the catalog key
- [Advisor: manual install](manual-install.md) — the no-agent path, same key requirement
- [Advisor: what the agent does](what-the-agent-does.md) — credential handling and
  revocation, for a security review
The catalog-key REST API and the org-scoped deploy API are documented in full internally
(`backend/docs/api-keys-api.md` and `backend/docs/deploy-api.md`). Those live in the private
platform repo and are deliberately not linked here — this page is published publicly, and a link
a reader cannot open is worse than a reference they can ask for. Ask your Multicloud contact if
you need either.

## How this document was verified

No deployed environment was reachable while writing this page, and self-serve signup is not open
yet regardless — so nothing here was exercised end-to-end against a running instance. Every claim
above was instead checked directly against the code that implements it:

- **Organizations, discovery, invitations, ownership, roles** — `backend/api-server/src/orgs_api.py`
  and `backend/api-server/src/org_identity.py` (the `/owners` group check, the per-slug — never
  flattened — ownership test, the by-domain discovery endpoint's own "never admits, never blocks"
  docstring, the free-mail exclusion list, the two-organizations-per-day cap).
- **Invitations not granting ownership** — `backend/api-server/src/keycloak_admin.py`'s
  `invite_member` (adds a member only; the creator alone is put into `/owners`, in
  `orgs_api.create_org`) and `add_to_group`.
- **Request to join: that it only asks, that an owner's confirmation is the only thing that admits
  anyone, the seven-day link, the one-hour repeat window and the daily cap** —
  `backend/api-server/src/orgs_api.py`'s `request_to_join` and `approve_join_request` (the approve
  path invites the address carried inside the signed link, never one handed to it by a browser),
  `JOIN_TOKEN_TTL_SECONDS` in `backend/api-server/src/join_tokens.py`, and the by-domain endpoint
  above them, which is what carries the never-displayed identifier the button sends. The page an
  owner lands on lives in the website repo and, like the revoke button below, is confirmed in source
  in an unmerged worktree rather than observed in production.
- **Catalog key mint/list/rename/revoke, the shown-once response shape, the 10-active-key cap, and
  "any owner regardless of who minted it"** — `backend/api-server/src/api_keys_api.py` and the
  `CatalogKeyCreatedResponse` / `ApiKeyRecord` / `CreateApiKeyRequest` models in
  `backend/api-server/src/schemas.py`.
- **Revoke is `POST .../revoke`, not `DELETE`, and takes effect within a minute** — the route
  registration in `api_keys_api.py` and the cache-eviction call (`invalidate_api_key_cache`) right
  after the commit; the cache itself is an in-process `TTLCache` (`auth.py`), so eviction only
  reaches the worker that served the revoke. **`replicaCount: 1` is not one process** — the
  entrypoint defaults `MULTICLOUD_API_WORKERS=2` — so the bound comes from
  `MULTICLOUD_API_KEY_CACHE_TTL`, set to 60 in
  `data/k8s/charts/multicloud-api/values.yaml`, not from the replica count.
- **Deploy keys still require an operator, not self-serve** — `backend/api-server/src/deploy_keys_api.py`,
  whose issuance, listing, and revocation routes all gate on the caller holding the
  `multicloud-admins` realm role.
- **Self-service revocation exists as a real UI, not just an API** — the `/account` page's catalog
  keys panel (`components/account/CatalogKeysPanel.tsx`, built in a separate worktree of the
  website repo per this plan's Task 13) calls this same revoke endpoint from a "Revoke" button.
  That worktree is outside this repository and its own commit is not yet merged, so treat this one
  claim as confirmed-in-source-but-not-yet-shipped-to-production, same as everything else on this
  page until signup opens.

One thing this page deliberately does **not** claim: that every catalog key Multicloud has ever
issued cannot be recovered. That's true for every key minted through the flow described above. It is
not true of a small number of older rows created before this model existed, which authenticate by
their database row id rather than a hash — an internal detail with no effect on how you use a key
you mint today, and one that is being fixed separately.
