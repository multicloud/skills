# Advisor MCP reference

The Advisor already exposes a web console and a JSON API. The MCP server exposes the same truth to
an AI agent, plus the procedural knowledge that used to live in a human's head: what is missing,
what it costs you, exactly which grant fixes it, and what to run next.

This page is for two audiences: you are on an MCP client other than the one our skill targets, or
you want to drive the Advisor directly instead of through a skill.

## The read-only guarantee, and how to verify it

The Advisor never writes to a cloud on your behalf through MCP. That is not a policy — it is an
absence you can check in about ten seconds:

```
tools/list
```

There is **no `submit_*` tool, no cloud-write tool, and no tool that accepts a credential of any
kind.** If your client shows you one, you are not talking to this server.

> **All 15 tools are live.** Five read (`get_readiness`, `get_build_status`,
> `get_report`, `get_workloads`, `get_quota_report`), seven plan (`plan_repack`, `diagnose`,
> `get_required_iam`, `preflight`, `plan_remediation`, `plan_quota_requests`,
> `plan_grant_requests`) and three act (`refresh`, `set_quota_selection`, `set_discount`).
> `tools/list` is the authority on that count, not this page — and whatever it returns, none
> of it is a `submit_*`, a write, or a tool that takes a credential.

The agent does act on your clouds — with *your* credentials, from *your* machine, through the CLIs
you already have. Those credentials never enter the cluster and never reach the Advisor.

One clarification for security reviewers, because the chart contains a write path: the Advisor
does ship an opt-in, default-disabled quota-*submission* feature (`quotaRequests.*` in
`values.yaml`, backing `POST /quota/requests/submit`). It is reachable only from the console's own
per-batch confirmation UI, its routes return 404 unless you explicitly configure write credentials
per cloud, and it is **not exposed through MCP and will not be**. The agent path and that path are
separate by design.

## Connecting

### Where the server runs

In your cluster, inside the Advisor pod, on the same port as the console. It is not a second
deployment, not a sidecar, and it has no Ingress of its own.

| | |
|---|---|
| **Reached over** | The same `kubectl port-forward` tunnel as the web console |
| **Internet-exposed** | Never. Not just off by default — the chart *refuses to render* `mcp.enabled` together with anything that publishes the Service: `ingress.enabled`, or a `LoadBalancer`/`NodePort` `service.type` (see the exposure warning below) |
| **Transport** | Streamable HTTP, matching our existing MCP server, mounted on the Advisor's own HTTP port at **`/mcp/`**. Stateless — there is no session id to hold, so a client survives the pod being rescheduled |
| **Authentication** | None on any Advisor HTTP route — see the warning below |
| **Host header** | Loopback only. Anything else gets **421 Misdirected Request**, so point your client at `127.0.0.1` or `localhost` — never a hostname alias for them |

### The port-forward

The Service is named `<release>-advisor` and listens on `service.port` (8080 by default). With a
release called `audit`:

```bash
kubectl port-forward svc/audit-advisor 8080:8080
```

That single tunnel carries the console (`http://localhost:8080/`), the report, and the MCP
endpoint.

### Client configuration

Point any MCP client that speaks Streamable HTTP at the forwarded port:

```json
{
  "mcpServers": {
    "multicloud-advisor": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp/"
    }
  }
}
```

The trailing slash matters: `/mcp` answers with a redirect to `/mcp/`, and not every client
follows one on a POST. The host must be `127.0.0.1` or `localhost` — the server validates the
`Host` header on every request and answers 421 to anything else, which is deliberate (see the
exposure warning below).

**Auditing more than one cluster at a time?** Give each cluster its own local port and its own
client entry. Port-forward collisions are silent and produce confidently wrong answers about the
wrong cluster. Verify which cluster you are attached to *through the MCP connection itself* —
`get_readiness` reports the cluster it actually sees — never from the local port number.

### Exposure warning

**The Advisor has no authentication on any HTTP route.** That is acceptable on the shipped
defaults because the only way in is `kubectl port-forward`, so your Kubernetes RBAC is the gate:
if you cannot port-forward to the pod, you cannot reach the MCP server.

It stops being acceptable the moment the Service is published beyond the cluster. There are two
ways to do that, and both publish *everything*:

| Setting | What it publishes |
|---|---|
| `ingress.enabled=true` | The Ingress routes `/` to the whole Service |
| `service.type` anything but `ClusterIP` or `ExternalName` | The Service itself, port 8080, directly |

In both cases every route goes out at once — there is no way to route one path differently and exclude
`/mcp/`, and therefore no "authenticate just the MCP path" setting.

The chart resolves that by making MCP and publication **mutually exclusive at template time**.
`mcp.enabled` defaults to `true`; combining it with any of the three makes `helm install`/`helm
upgrade` **fail**, naming which one caused it and the fix:

```
--set mcp.enabled=false
```

You keep the published Service and drive the Advisor by hand, or you keep the Service
cluster-internal (`service.type=ClusterIP`, `ingress.enabled=false`) and keep the agent path over
`kubectl port-forward`. There is no configuration in which the chart renders an unauthenticated
MCP endpoint reachable from outside the cluster.

`service.type` is checked as an **allowlist**, not a list of forbidden values: while MCP is
enabled, the chart accepts exactly `ClusterIP` and `ExternalName` (neither publishes an endpoint
of its own) and refuses everything else. That covers the wrong letter case, a value carrying stray
whitespace from an interpolated CI or GitOps variable, and any Service type Kubernetes ships in
future — none of which a list of *bad* values can cover. The check runs against the same
normalised string `templates/service.yaml` renders, so what the guard inspects is what the API
server receives.

`mcp.enabled` must also be a real boolean. `--set-string mcp.enabled=false` (or a CI variable
interpolated with quotes) is rejected rather than accepted, because the pod treats any non-empty,
non-`false` value as *enabled* — so a quoted `"false"` would leave the server running while your
values file read as though it were off. Leaving the key unset, `null` or empty is fine and means
the default.

> **Breaking change for an existing install.** A release already running `ingress.enabled=true`,
> or a `LoadBalancer`/`NodePort` Service, starts failing `helm upgrade` at **0.4.0**, the version
> that introduced this. That is by design — MCP ships enabled by default, so the alternative was
> for the upgrade to silently make an unauthenticated endpoint reachable from outside the cluster.
> Add `--set mcp.enabled=false` (or set it in your values file) and the upgrade proceeds.
> Full version-boundary note: [What changed in 0.4.0](manual-install.md#what-changed-in-040).

A second safeguard at runtime: the MCP server validates the `Host` header on every request and
answers **421 Misdirected Request** to anything that is not loopback. Note what that does and
does not give you — it is DNS-rebinding protection, so it inspects the `Host` *header*, not who
you are. Through an Ingress the controller forwards the real hostname and the request genuinely
gets 421; a client that could reach a `LoadBalancer` directly would simply send
`Host: localhost:8080` and pass. That asymmetry is exactly why the chart refuses to render the
`LoadBalancer` case at all rather than relying on this.

`kubectl port-forward` binds to localhost by default. Anything running on your machine can reach
that port. Treat it like any other local admin socket.

## Result conventions

The server follows the same house style as the Multicloud catalog MCP server, for the same reason:
an agent pays for every token it reads.

| Convention | What it means for you |
|---|---|
| **Columnar list results** | Every list-shaped result is `{columns: [...], rows: [[...]], row_count: N}` rather than an array of repeated-key objects. Field names are sent once. Roughly 40–60% fewer tokens on large result sets. |
| **Two identity conventions, not one** | A **build-derived** figure (`get_report`, `get_workloads`, `get_quota_report`, `plan_repack`) is wrapped with `report_identity: {generated_at, levers}` — the build stamp AND the lever state it was computed under, both always present (`levers` is `null` for an unscoped/base view). `get_quota_report` additionally carries `fleet_generated_at` inside `report_identity`: its sizing depends on a SECOND build (the savings context it was packed against), so that stamp gets its own explicit key rather than being folded into `generated_at`, which means the quota collection's own timestamp everywhere else. A **cache-derived live** figure (`get_readiness`) instead carries `fresh_as_of` + `age_seconds`, deliberately a different shape rather than a variant of the same one: `fresh_as_of` advances on every ~30-second re-probe even when nothing about the cluster changed, while `generated_at` only ever moves forward, and changes only when the report itself changed — folding the two into one field would teach you a rule that is not actually true. `diagnose` carries BOTH, because it joins both kinds: `fresh_as_of`/`age_seconds` for the readiness cache, and `report_identity.generated_at` for the savings build its `data_gaps`/quota flags came from (`null` when no audit has run yet — the readiness half still works with zero builds). A payload that already *is* provenance (`get_build_status`) needs no wrapper at all. Quote every stamp present alongside any number; never restate a figure without them. |
| **Summary by default** | The full audit report is large. `get_report` returns a summary unless you ask for the full document. |
| **Defensive parameter handling** | Some clients wrap argument values in a `{"type": ..., "value": ...}` descriptor. The server unwraps these rather than failing, so a quirky client still works. |
| **Polling, not blocking** | Long builds are polled with `get_build_status`, not waited on inside a tool call. |

## Read tools

Cheap unless noted, idempotent, no side effects. Safe in a loop — see the freshness note on
`get_readiness` below.

| Tool | Purpose | Parameters | Returns | Cost | State |
|---|---|---|---|---|---|
| `get_readiness` | Is the Advisor wired correctly, what fidelity (how completely the fleet can be identified and priced) is active, what is missing | none | Overall status (`ready` / `partial` / `not_ready`), whether a report is computable, node coverage %, identified vs total nodes, pricing basis (`actual` / `mixed` / `list`), catalog reachable/authenticated, RBAC checks, per-cloud identification counts, tier states, utilization source **and its quality**, quota tier state per cloud, per-cloud **account identity** (`accounts` — the GCP projects / Azure subscriptions / AWS account ids seen — and `account_source`, see below) | Cheap when cached (see below) | Read-only |
| `get_report` | The savings counterfactual — what the same workloads would cost placed the cheapest way | `detail`: `summary` (default) or `full` | Generated-at stamp, cluster summary, waste triangle (the split between capacity you pay for, capacity requested and capacity used), discount basis, per-workload findings, data gaps, deliberately excluded workloads, the headline fleet plus the low-risk and conservative anchors, the cloud/region picker universe, right-sizing recommendations, quota flags | Always cheap — this tool never triggers or blocks on a build. If no audit has been built yet it returns `available: false` immediately; poll `get_build_status` | Read-only |
| `get_workloads` | Bill-by-workload findings, for scoping conversations | none | Per-workload attributed spend and savings, ranked by migration-weighted savings | Cheap once the report is cached | Read-only |
| `get_quota_report` | Quota inventory and adequacy verdicts | none | Collected inventory, your saved selection, per-quota recommendations, per-cloud collection status, the `required` / `mandatory_required` split — what the fleet **cannot run without** versus what is merely worth having open — and a `report_identity` naming BOTH builds behind the numbers (the quota collection's own stamp, plus `fleet_generated_at` for the savings context it was sized against) | Always cheap — this tool never triggers or blocks on a collection. If no quota audit has been built yet it returns `available: false` immediately; poll `get_build_status` | Read-only |
| `get_build_status` | Both build state machines | none | Savings build state (`idle` / `building` / `ready` / `error`) with its generated-at stamp, plus real per-cloud quota-collection progress that increments only as regions actually complete | Cheap. Never starts a build | Read-only |

**Freshness on `get_readiness`.** The underlying route (`GET /status.json`) computes the full
assessment — cluster collection, a live catalog probe, metrics discovery, and every configured
cloud's quota probe — once and caches it, rather than re-running all of that on every call. The
cache is invalidated explicitly on the events that actually change readiness (a newly-reporting
node, `/refresh`, a discount change, a quota rebuild) plus a 30-second TTL backstop for what none
of those catches — mainly a credential Secret rotated under the pod. Every response carries
`fresh_as_of` (the ISO-8601 instant the cached assessment was computed) and `age_seconds` (how
old it is right now), so you can tell a 30-second-old answer from a fresh one instead of assuming.
This makes `get_readiness` safe in a tight verification loop — it costs one real probe, not one
per poll. (The human-facing console at `GET /` always forces a fresh compute instead of reading
this cache — a person pressing reload expects fresh.)

**Verified versus reported account identity.** A grant request has to name the cloud account it
is for, and `account_source` is how you tell a checked answer from a claimed one. It is
`"provider_id"` when the account came off the Kubernetes-authored providerID (the GCP project or
Azure subscription the kubelet itself wrote onto the Node) — nothing self-reported it, so treat
it as verified. It is `"introspection"` when the account came only from the Tier-2 IMDS DaemonSet
posting to `/introspect`, which — like every other route on this server — carries **no
authentication**; any pod on the cluster network could POST a fabricated value. This is the only
path for an AWS account, because an AWS providerID (`aws:///<zone>/<instance-id>`) never carries
one. `"none"` means neither source resolved it. Treat `"introspection"` as a claim to confirm with
the human before it appears inside a grant request, never as an already-checked fact — do not
special-case AWS as trusted just because it is the common case.

`account_source` is computed per cloud, over every node in it, and fails **closed** (when in doubt it claims less, not more): a cloud reads
`"provider_id"` only when every account contributed under that cloud came from a providerID. One
node reporting its account over `/introspect` pulls the *whole cloud's* label down to
`"introspection"`, even if every other node in it was verified — under-claiming costs one
confirmation prompt, and over-claiming costs a grant made against the wrong account.

**Caveat on the severity split.** The quota report distinguishes *blocking* (the fleet as
described cannot run) from *recommended* (worth having open, but nothing breaks today), exposed
as the `required` / `mandatory_required` fields. Read the severity; do not infer it from the
presence of a recommendation.

## Plan tools

The knowledge layer. Seven tools. These compute answers and produce executable steps. **None of
them accept a credential**, and none makes a cloud call with a credential you have not already
opted in — the only credentials in play are the `quota.{aws,azure,gce}` Secrets Tier 4 uses.

Two things do reach a cloud once such a Secret exists, and it is worth being precise about which.
`preflight` makes its own reads (the GCP org policy, the Azure resource-provider registration).
And `diagnose` and `preflight` both read the shared readiness assessment, whose computation
includes a quota probe against every configured cloud — so on a cluster with no cloud credential
configured they are genuinely network-free, and on one with a credential they are not. The
remaining four (`plan_repack`, `get_required_iam`, `plan_remediation`, `plan_quota_requests`)
make no cloud call under any configuration; `plan_grant_requests` calls `preflight` internally
rather than a cloud directly. All seven are cheap, idempotent, and safe to call repeatedly while
you decide.

| Tool | Purpose | Parameters | Returns | Cost | State |
|---|---|---|---|---|---|
| `diagnose` | The flagship. What is wrong, in priority order — call this FIRST | none | Ordered gaps, most-costly-first (a cluster that cannot price anything, then degraded fidelity, then an unconfigured capability, then advisory). Each carries what it costs you in the customer's own terms, the remediation id, the privilege it needs (`"you, right now"` vs your security/billing admin), and `validation` — whether that remediation has actually been proven. Only the Tier-3/Tier-4 rows carry `cloud`/`capability`; the rest are `null` on purpose — no invented IAM dimension. `available` is false when this cluster's nodes could not be listed at all: on that branch every cluster-derived row was never checked, so an empty `gaps` does not mean everything is fine and `why` says what failed | Cheap — pure join over the cached readiness assessment plus the last report's data gaps and quota flags. It triggers no build and holds no credential of its own, but the readiness assessment it reads probes every cloud a Tier-4 Secret is configured for, so it is only network-free until the first credential lands | Read-only |
| `get_required_iam` | The exact, live, version-matched access needed | `cloud`, `capabilities[]`, optional `have[]` | One merged least-privilege policy for the whole capability set, with **a reason per action**, plus both maturity fields (`validation` — does the read path work; `grant_validation` — have these exact grant commands been run). Asking for more than one capability returns a UNION `policy_json` for "what would both need?" but `is_view: true` and empty `grant_commands` — it is never installed directly — with `procedures[]` carrying one complete, self-sufficient request per capability instead. A single capability has no separate procedure: `is_view` is `false` and the result already IS the request. Supports a delta form via `have`: "add these actions to the policy you already have". When that delta comes out empty, `nothing_to_grant: true` and `why` say so and BOTH command lists are withheld — there is nothing to grant, and the revocation commands would strip access still needed for what they already hold | Cheap | Read-only |
| `preflight` | Every foreseeable blocker, checked before any request names it — call this after `diagnose`, before filing anything | optional `clouds[]` (accepts the "gce"/"gcp" synonym; defaults to the clouds this cluster's nodes belong to) | One row per blocker: GCP's key-creation org policy, Azure's `Microsoft.Quota` resource-provider registration, Azure's support-plan tier, region enablement per cloud, this cluster's OIDC issuer, and the Advisor's own namespace PodSecurity level. Read three fields on every row: `detected` (is it present), `detectable` (can we even tell — Azure restricted regions and GCP region enablement have NO programmatic detector, so this is `false` rather than a false-clean `true`), and `self_serviceable` (can the driver — the person running this audit — fix it themselves, without a ticket). `route` names the safe alternative — usually workload identity, or "not self-serviceable, here is who to ask". `clouds_covered` says which clouds actually got probed; an empty list means every cloud-specific row was SKIPPED, not that they all came back clear | Cheap. Makes read-only cloud calls of its own, for clouds you already gave a Tier-4 credential to — and, like `diagnose`, reads a readiness assessment that probes those same clouds | Read-only |
| `plan_remediation` | Turn a gap into steps | `remediation_id` (exactly as the gap carries it) | Ordered executable steps with the Secret-before-`helm upgrade` ordering baked in, plus a verification assertion to re-run afterwards | Cheap | Read-only |
| `plan_quota_requests` | Exactly what would be filed, and how | `keys[]` | Per-item drafts: cloud, region, quota id, desired value, justification text, and the **exact API call** each request would make. Zero cloud calls — it reads only the already-cached quota report. `report_identity` names both builds the `desired` figure came from (`generated_at` = the quota collection, `fleet_generated_at` = the savings build it was sized against) — re-check both before a human files the number. Every Azure call also carries a `routing:` line in its `detail` saying whether the `Microsoft.Quota` PATCH is believed to be the right mechanism, with the portal route to use when it is not — labelled as the Advisor's own classification, since Azure publishes no adjustable flag | Cheap | Read-only |
| `plan_grant_requests` | The grant-request document itself, ready to forward | optional `clouds[]`, optional `capabilities[]` (defaults: this cluster's own clouds, both capabilities) | One Markdown artifact per (cloud, account, capability) — policy, a reason per action, blast radius (what else this access could reach), data handling, expiry recommendation and revocation, all in one document a driver forwards into a ticket or an email unchanged. Calls `preflight` itself first and **annotates rather than withholds**: every artifact always carries its `markdown`, and what the preflight found for that exact (cloud, capability) travels as `caveats[]` *and* is rendered into the document, so the approver reads the caveat. Each caveat carries its own `state` (`present`, `clear`, `unchecked` — a detector exists but could not run — or `undetectable` — no detector exists), plus `detail`, `route` and `self_serviceable`. A cloud with no resolvable account gets an explicit placeholder account and `account_source: "none"` rather than a blank; no clouds at all returns `available: false` with a `why`, never a bare empty list | Cheap — the only network cost is the `preflight` call it makes internally | Read-only |
| `plan_repack` | What-if against the levers | lever state: right-size on/off, clouds on/off plus an optional subset, regions on/off plus an optional subset, spot on/off, and a list of workloads to exclude | The cheapest fleet that packs your workloads under those constraints, plus each lever's marginal dollar impact and the delta versus the current default. Never rebuilds — returns `available: false` if no audit is cached yet. See caveat | Always cheap — in-memory only, never triggers a build | Read-only |

**Why `get_required_iam` is a tool and not a document.** A stale IAM action list is not a
cosmetic problem. In July 2026 a single missing `ec2:Describe*` action denied one call and wiped
an entire region's quota limits from a live audit — the report looked clean and was wrong. The
action list is therefore served by the running Advisor, version-matched to the code that makes the
calls, so it cannot drift from what is actually required. Never hand-merge policies across
capabilities: a missing action produces a silent wrong answer, and an over-broad ask gets rejected
and costs you a review cycle. That is also why a multi-capability call never hands you only a
union policy: `procedures[]` gives you the two separate, complete requests, precisely so
you are never the one merging them.

**Why `preflight` exists at all.** Two requests per cloud account is the designed number; a
third is a defect. Without it, three things would surface only when the driver actually tried the step: a GCP org
policy that blocks the key download that `get_required_iam`'s own procedure assumes, an
unregistered Azure resource provider, and a support plan that cannot open a ticket. That is
precisely a third trip to whoever approved the first two. `preflight` finds those before anything is asked.
Its most important field is not `detected`, it is `detectable`: Azure restricted regions and GCP
region enablement have no programmatic detector at all, and reporting them as clear would be a
lie your driver could not tell apart from the truth — so those rows report `detectable: false`
with an explanation instead of silently agreeing with a clean bill. Its most VALUABLE field is
`self_serviceable`: registering an Azure resource provider or enabling an AWS opt-in region is
usually something the driver can do with rights they already hold, and routing either into a
ticket would itself be the third-trip failure this tool exists to prevent.

**Why `plan_grant_requests` never mentions the sibling capability.** Pricing and quota are
independently actionable: if pricing is denied or stalls, quota still lands and the analysis
continues on a list-price baseline with the caveat labelled, and neither is a prerequisite for
the other. So each artifact is scoped to exactly one capability and never references the other
by name — naming one inside the other's document is precisely the kind of coupling that lets
whichever approver is slower gate the one that was ready sooner. It also never emits a third
request per cloud account: a region-, quota-, or tier-scoped variant is a defect in `preflight`,
not a normal step, and the fix is to improve `preflight`'s detection, never to add a request.

**Why a preflight finding never withholds the document.** `plan_grant_requests` calls
`preflight` and puts what it found *inside* the request, labelled — it does not hold the request
back. Both grants are produced and sent simultaneously; nothing waits on anything else. Holding
one back would recouple exactly the approval delays the two separate requests exist to
decouple, and it would do so on findings the approver in question usually cannot act on: an
opt-in region that is not enabled has nothing to do with a billing-scope role, and the person who
approves quota visibility does not own your cluster's OIDC issuer. So the caveat goes to the
human who can weigh it, in the document they are already reading. Read each caveat's `state`
before you summarise it: `clear` means checked and fine, `undetectable` means nothing can check
it at all, and treating the second as the first is the exact mistake `preflight` exists to
prevent.

**Caveat on `plan_repack`.** It is side-effect-free and in-memory over the candidate frontier (the set of candidate fleets) the last
completed savings build cached — no cluster access, no catalog I/O, no state changed — so it is
safe to call as many times as the conversation needs. It **never triggers a build.** If nothing
is cached yet (no audit has completed, or the cache was invalidated by a pod restart, a discount
change, or a newly-reporting node) it returns `available: false` and says so rather than
rebuilding — poll `get_build_status` and wait for `ready`, then ask again. This is deliberately
different from the web console's own `POST /repack`, which *does* rebuild on a cold cache so a
lever toggle in the browser never dead-ends: a what-if an agent asks mid-conversation is a
conversation move, not a request to start a multi-minute, catalog-hitting audit.

## Act tools — Advisor-local only

These change state **inside the Advisor**. None of them reaches a cloud. All three are worth
reading carefully before you wire them into anything automatic.

| Tool | Purpose | Parameters | Returns | Cost | State |
|---|---|---|---|---|---|
| `refresh` | Rebuild the savings report and/or the quota audit | `scope` (required: `"savings"`, `"quota"` or `"all"`) | Which scopes are (re)building, and where to poll | **Expensive** | **Globally invalidating** |
| `set_quota_selection` | Save your fleet-size answers and audit scope | `clusters`, `peak_nodes`, `node_vcpus` (all **required** — the fleet-size questionnaire), plus optional `large_scale`, `gpu_classes`, `excluded_regions`, `overrides` | Whether it persisted, the selection as saved | Usually cheap | **The one durable write** |
| `set_discount` | Price against your negotiated rate instead of list | `mode` (required), `effective_discount` | The applied mode and rate | **Expensive** | **Globally stateful** |

### `refresh` — invalidates for everyone

Refresh drops the cached report and rebuilds it. It does not have a "just for me" mode: every
other caller, including anyone with the console open in a browser, loses the cached result at the
same moment. Scope it explicitly — a savings refresh and a quota refresh are on separate schedules and
refreshing one does not rebuild the other.

Both the savings rebuild and the quota rebuild return immediately and run in the background —
this tool never blocks on the collection it starts. Poll `get_build_status` for real progress
rather than retrying; calling `refresh` again while a scope is already rebuilding does not start
a second, concurrent collection — it recognizes the in-flight build and leaves it alone.

### `set_discount` — globally stateful, and it triggers a re-audit

This is the most dangerous tool on the server, and its description says so. It:

- changes the pricing basis **for every caller**, not just your session;
- invalidates the cached report and kicks off a full re-audit in the background — like `refresh`,
  it returns immediately rather than blocking on that rebuild, so the `effective_discount` it
  hands back is the override just recorded, not proof the report has been recomputed with it yet
  (poll `get_build_status`, then re-read `get_report`);
- persists only in memory, so a pod restart silently reverts it to the deployed default.

Use it when a human has asked to see their negotiated rate. Do not use it to explore. `mode` is
required precisely so that a malformed call cannot silently flip your pricing basis; passing
`default` clears the override.

Unlike `refresh`, calling `set_discount` again while a rebuild from the previous call is still
in flight does **not** reuse it — it starts a genuinely new rebuild under the new
discount instead, on top of whatever was already running. That is deliberate: the build already
in flight was computing under the *old* discount, so waiting for it would silently keep serving
the stale rate for however long it takes to finish. The cost is a short window where two audits
run at once; the one that lands is always the most recent call, regardless of which finishes
first.

### `set_quota_selection` — the only thing that survives a restart

Your saved selection is written to a namespaced ConfigMap. Everything else in the Advisor —
the report, the node introspection map, the record of what was submitted — lives in memory and is
lost when the pod restarts, which on ephemeral nodes is routine.

`clusters`, `peak_nodes` and `node_vcpus` are required on every call, with no default to fall
back on: fleet size is asked, never assumed, because a new account has zero usage to infer it
from. Derive a starting estimate from the packed fleet you already see in `get_report`, show the
human that number, and let them correct it before you call this — never invent one and never
leave it silently defaulted. The call replaces the whole saved selection, not just the field you
meant to change, so pass every field you want kept.

Two behaviours worth knowing beyond the fleet-size answer.

**The tool recomputes nothing.** It writes the ConfigMap, drops (or supersedes) the cached quota
report, and hands you back `next: "call refresh(scope='quota') then poll get_build_status()"`. Do
that; do not assume the next `get_quota_report` is already re-scoped. The narrow-versus-widen fast
path exists on the console's own `POST /quota/selection` route, not on this tool. On that route, a
save that only *narrows* scope (smaller fleet, fewer regions, deselected classes) recomputes from
the cached inventory immediately with no cloud calls, and only a *widening* save falls back to a
full re-collection. Driving the tools directly means driving the rebuild yourself.

**A failed save is always quiet** on a cluster-access problem: it degrades to `saved: false` with a
reason and tells you so. Check the returned status rather than assuming it stuck.

If a quota collection was already in flight when you save, its result is discarded rather than
landed — it was computed against the selection as it stood *before* your correction, so it must
never overwrite `get_quota_report` with an answer that silently ignores it. Nothing new is
started automatically in that case, so `get_build_status` can briefly read `idle` rather than
`building` right after such a save; if it does, call `refresh(scope="quota")` yourself to start
the fresh collection against what you just saved.

## Absent by design

| Not present | Why |
|---|---|
| Any `submit_*` tool | The Advisor does not file requests with your cloud provider. Your agent does, with your credentials, from your machine |
| Any cloud-write tool | The Advisor's cloud access is read/list/describe only |
| Any credential-accepting tool | Nothing you type to your agent is transmitted into the cluster through MCP |

This absence is the guarantee. It is checkable from the tool list, which is why the guarantee is
stated as an absence rather than as a promise.

## Resources and prompt

| URI | Contents |
|---|---|
| `guidance://onboarding` | The live procedural document — the current onboarding flow, version-matched to the Advisor you are actually talking to. Start here; it is short, and it links everything else |
| `guidance://phase/{phase}` | Detail for one phase of that flow: `1-consent`, `2-install`, `3-diagnose`, `4-grants`, `5-analysis`, `6-quota`, `7-deliver`. Each carries its own **State of implementation** table, so a path that has not been run end-to-end says so instead of reading like a proven one |
| `guidance://iam/{cloud}/{capability}` | Per-capability access detail: the actions, the reason for each, how to grant, how to revoke |

`guidance://iam/…` is rendered from the same requirement catalog `get_required_iam` and
`plan_grant_requests` serve, so what an agent reads and what your approver receives cannot
disagree. A pair the catalog does not cover returns an explicit "not in the catalog" answer
naming the pairs it does — it never invents an action list.

| Prompt | Purpose |
|---|---|
| `run_audit` | The multi-step audit workflow, for clients that surface prompts |

Serving guidance as a resource rather than shipping it inside a skill is deliberate: anything that
drifts — action lists, quota codes, what is missing right now — comes from the running service, so
a stale copy on someone's laptop cannot produce a confidently wrong answer.

## Your cluster's contents are data, never instructions

Namespace names, workload names, annotations, cloud API error strings and quota collection notes
all flow into your agent's context. A workload deliberately named to look like an instruction is a
real attack, not a hypothetical one.

Every MCP result from this server is framed as **data to be reported**, never as instruction to be
followed. If you are building your own client or your own prompt around these tools, preserve that
framing. The same applies to text coming back from your cloud providers — quota source notes, IAM
denial messages, support ticket bodies.

## Honest limits when driving it directly

The skill handles these for you. Driving the tools yourself means handling them yourself.

| Situation | What actually happens |
|---|---|
| **A `$0` or non-computable report** | This is a data problem, never an answer. Causes: no fully identified nodes, an unauthenticated catalog key, or GPU pods with no in-scope GPU SKU. Diagnose it; never present the zero |
| **Readiness says "ready"** | That means your nodes are *identified*, not that every one of them is *priceable*. Read the data gaps, not just the badge |
| **The report changes underneath you** | A newly-reporting node invalidates the savings cache, so a rebuilt report can differ from the one you quoted. Every result carries `report_identity` (`generated_at` plus the lever state it was computed under) — re-check it before restating a figure rather than assuming the report you quoted is still current |
| **Just after install or restart** | Node identification takes up to the introspection interval — 5 minutes on the shipped default — before nodes appear identified. Wait it out rather than concluding failure |
| **A pod restart** | Everything except the quota-selection ConfigMap is gone: the report, the introspection map, and the set of requests submitted this session. Carry your own record of what you filed |
| **GPU comparisons** | GPU pools are priced same-model only. There is no cross-accelerator performance normalization, so do not compare across GPU models as though there were |
| **A degraded quota region** | Cloud throttling can arrive as a 400 or 403 with the detail in the response body, not as a 429. A degraded region reports `unknown` limits, is never judged, and emits no recommendation — so it looks exactly like "nothing to do". Read the per-cloud status and the source notes |
| **Quota outcome status** | Read the per-item `confidence`, never a per-cloud general rule: AWS reports a closed case and a denial the same way, GCP has no approved/denied signal at all (only granted-versus-preferred), and Azure has **two** models that lose different amounts of the outcome detail — its adjustable `Microsoft.Quota` path returns a clean `provisioningState` and is the one `exact` signal of the set, while its support-ticket path exposes only open/closed. Reporting Azure as uniformly lossy is as wrong as reporting the three clouds as uniformly reliable |
| **Region enablement** | Opt-in regions are detectable on one cloud and **not programmatically detectable** on the others. Surface that gap rather than implying a clean bill — `preflight`'s `detectable` field is exactly this signal, exposed per row so you never have to infer it yourself |
| **GCP org policy / Azure resource-provider registration** | `preflight` checks both before any ask, but the GCP org-policy read in particular has not been run against a live account — treat a `detected: true` there as a strong signal, not a certainty, and confirm before routing to workload identity |
| **`preflight`'s `namespace-podsecurity-level` row** | Needs `get` on the cluster-scoped `namespaces` resource, which no chart shipped for the Advisor grants — deliberately, so this row always reports "could not check". Use your own `kubectl` before installing instead of waiting on it. Only a ClusterRole an operator widened by hand gets a genuine answer here |
| **API-rate quotas** | Token-bucket quotas get no floor and no demand attribution, and their catalog ids are synthetic rather than real quota codes. They are visibility only — do not attempt to file them |
| **PDF export** | Starts a separate headless browser process per request, with no caching. Fine for a deliverable, not for a loop |
| **Catalog calls** | The Advisor caps its own catalog concurrency and retries on throttling. Do not run your own catalog queries in parallel with a running build |

## Two `preflight` rows to read carefully

Listed here so you can chase them rather than discover them:

- the GCP org-policy read inside `preflight` (whether
  `constraints/iam.disableServiceAccountKeyCreation` is enforced) has not been run against a
  live account. Treat its `detected` value as a strong signal, not a certainty, until that
  changes. The Azure resource-provider registration read next to it is better established —
  `GET providers/{namespace}` is core, long-stable ARM.
- `preflight`'s `namespace-podsecurity-level` row needs `get` on the cluster-scoped
  `namespaces` resource, and **no chart shipped for the Advisor grants it** — a deliberate
  choice, not an oversight (widening cluster-wide RBAC to land one probe was rejected). So this
  row always reports "could not check", identically to a machine with no cluster access at all,
  and the authoritative precondition check is your own `kubectl`, before you install — see
  [troubleshooting.md](troubleshooting.md#the-introspection-pods-never-start). Only a
  ClusterRole widened by hand, after install, gets a genuine answer from this row instead.

The live `tools/list` and the running server's own tool descriptions are authoritative over this
page.
