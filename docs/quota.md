# Quota: finding the provisioning wall before you hit it

## Why this matters

A saving you cannot provision is not a saving.

Cloud quotas are per-region and, on a new account, usually generous only where you already
run. Every other region starts small — and GPU families almost always start at **zero**. You do
not discover this while planning. You discover it at the moment the scheduler tries to place
nodes in a cheaper region, which is *after* you have committed to the move.

The quota audit turns that wall into a checklist you can clear before it costs you anything.

## What the audit looks at

Every region of every cloud you have connected, minus any you exclude. For each region it reads
the quotas that actually govern the fleet the report recommends:

| Class | Examples | Why it is audited |
|---|---|---|
| Aggregate vCPU pools | Regional total, spot / low-priority pool | The first ceiling any fleet hits |
| Per-family vCPU quotas | AWS X/F/High-Memory pairs, Google Cloud per-family CPU metrics, Azure family vCPUs | A zero here silently removes the cheapest option |
| GPU quotas | Per accelerator class, on-demand and spot | Start at zero nearly everywhere |
| Network object counts | VPCs/VNets, internet gateways, network interfaces, public IPs, security groups, route tables | The first quota an active multi-cluster estate (several clusters running at once) exhausts |
| Storage | SSD/disk capacity ceilings | Read for visibility |
| API request rate | Token-bucket limits on instance create/terminate churn | Read for visibility only — see [API-rate quotas](#api-rate-quotas-visibility-only) |

For each one it reads the **limit** and, where the cloud exposes it, the **usage**. If a cloud
does not return a value, it is recorded as unknown — never treated as a blocking zero.

Everything in this phase is read-only.

## The questionnaire: what you are asked, and why

The audit needs to know how big the fleet will be. It cannot infer that, and it does not
pretend to: **a new account has no usage history to infer from.** So it asks, with sensible
defaults pre-filled, and sizes everything from your answer.

What you are asked:

| Question | Default | What it means |
|---|---|---|
| **Concurrent clusters** | 1 | **Multicloud** clusters you plan to run — not your existing Kubernetes clusters. Drives network-object sizing. |
| **Peak nodes** | 8 | Peak concurrent nodes in your busiest region. |
| **Typical node size (vCPUs)** | 8 | Node shape. Peak nodes × node vCPUs is the vCPU figure everything else is sized from. |
| **High scale** | off | Turns on API request-rate buckets and large-count ceilings that only bind at high node counts or burst-heavy churn. |
| **GPU classes** | none | Which accelerator classes you actually run, and how many GPUs of each. See [GPU sizing](#gpu-sizing-per-class-never-blanket). |

The figures are **per busiest region**, and the resulting requirement is applied to *each*
audited region — because quotas are per-region and the scheduler is free to place the fleet in
any one of them.

What you are **not** asked, because it is how the platform always operates: spot-first with
on-demand fallback, multiple clusters, and public IPv4 endpoints. Those are assumed and audited
unconditionally. Only the *size* is asked.

Where a savings report already exists, the sizing also includes the fleet it actually packed,
and the capacity you already have in use. Your answer is a floor, not a cap.

### How the fleet estimate becomes a number

| Requirement | Sized as |
|---|---|
| Spot vCPUs | peak nodes × node vCPUs |
| On-demand vCPUs | the same figure — the fallback must absorb the whole spot fleet when capacity is reclaimed |
| VPCs / VNets | 2 + concurrent clusters (one isolated network per cluster, plus a shared baseline) |
| Internet gateways (AWS) | tracks VPCs 1:1 |
| Public IPs (Azure) | 2 × peak nodes — two static Standard IPs per node |
| External IPv4 (Google Cloud) | 1 × peak nodes |
| Network interfaces (AWS) | 2 × peak nodes |

Each recommendation then asks for the level at which the quota stops being called marginal (too close to the requirement to be safe) — 2×
the requirement, on spot pools and on-demand alike — rounded up to the increment that cloud
accepts. That is deliberately the same number the adequacy check uses: an ask sized below it
would be reported as still-marginal the moment it was granted, and you would be back in front of
the same approver for the difference.

## Two severities, and why the distinction is load-bearing

Every gap is graded **blocking** or **recommended**. They are not the same request, and
treating them the same is how a customer's quota requests stop being taken seriously.

| Severity | Means | Urgency |
|---|---|---|
| **Blocking** | The limit sits below what the fleet **as you described it** needs. Something you asked for cannot run. | Clear it before you move. |
| **Recommended** | The limit is fine for the fleet you described, but a cost-competitive instance family is offered in that region and a low limit quietly removes it from the scheduler's choice set. | Worth opening. Nothing breaks today if you skip it. |

A recommended item is an *opportunity*, not a defect: it widens the set of hardware the
scheduler may place you on. The generated request text says so explicitly — a "recommended"
draft tells the cloud it is not urgent.

Gaps are ranked blocking first, then by how far the limit sits below the requirement.

### What never becomes a request

Deliberate silences (cases where no request is drafted), so the output is only ever actionable:

- **Comfortable headroom.** A limit already at 2× the requirement produces nothing.
- **Hardware the region does not stock.** If the catalog shows no such family or GPU class in a
  region, the row is marked *not offered* and no request is drafted.
- **Quotas nothing needs.** A limit of 0 the fleet never touches is reported as *not sized*, not
  as a comfortable green — an honest "not judged", rather than a false pass.
- **Unreadable limits.** If a cloud did not return a value, the gap cannot be judged, so nothing
  is recommended. **This is a real blind spot** — see [when a region degrades](#when-a-region-degrades).
- **Azure per-family vCPU quotas, for the opportunity case.** A catalog SKU cannot be mapped
  reliably to its Azure family, so those quotas are audited and sized from real demand and GPU
  selection, but never from the "a cheaper family is stocked here" signal. AWS and Google Cloud
  per-family quotas do get that sizing.

## GPU sizing: per class, never blanket

There is no single GPU quota on any cloud. Each one splits accelerators across different
families and denominates them differently. So you pick the classes you actually run, and only
those quotas are audited and requested.

The classes:

| Class | Covers |
|---|---|
| T4-class · entry inference | AWS G/VT (g4dn) · Azure NCasT4_v3 · Google Cloud T4 |
| L4 / A10-class · modern inference | AWS G/VT (g5/g6) · Azure NVadsA10 v5 · Google Cloud L4 |
| A100-class · training | AWS P (p4d) · Azure NCads/ND A100 v4 · Google Cloud A100 |
| H100-class · frontier training | AWS P (p5) · Azure ND H100 v5 · Google Cloud H100 |
| Custom ML accelerators | AWS Inferentia / Trainium / DL (AWS only) |

A narrow, named ask auto-approves far more often than a blanket every-GPU-family request, which
reads as speculative and routes to manual review.

### How a GPU count converts

You state a GPU count. Each cloud is asked in its own unit, derived from the cheapest SKU of
that class actually stocked in that region:

| Cloud | What is requested |
|---|---|
| **AWS** | Family **vCPUs**, on both the on-demand and spot quota of that family: `ceil(GPUs ÷ GPUs per instance) × vCPUs per instance` |
| **Azure** | Family **vCPUs**, sized **per family** from a SKU belonging to that family — a class spanning two families (for example NCads H100 and ND H100) is sized separately for each, never from one shared representative |
| **Google Cloud** | The raw **GPU count** on the per-accelerator quota, **plus** the host **vCPUs** those instances consume on the shared or family CPU pool — a GPU grant without host vCPUs is unusable |

Two consequences worth knowing before you file:

- **AWS puts its whole P family into one quota pair** covering both A100 and H100. Raising it for one
  class also raises headroom for the other. The generated request says so.
- **Google Cloud has no requestable on-demand H100 quota.** Only the preemptible (spot) quota can
  be requested; on-demand H100 is a committed-use conversation. The recommendation states this
  rather than drafting a request that cannot exist.

If a region does not stock a class, that class simply contributes no request there.

## Filing a request: what actually happens

Requests are filed **only** for items you explicitly confirm. There is no automatic submission
path anywhere in the system.

Each request carries the same three things: the quota, the region, and the absolute new limit.
The limit is stated in whatever **that** quota counts — vCPUs for a vCPU quota, VPCs for a VPC
quota, TiB for a storage quota — and as a bare number where the cloud publishes no unit for it
(AWS reports `"Unit": "None"` for its object-count quotas). Free text works differently on
each cloud:

| Cloud | Mechanism | Your justification text |
|---|---|---|
| **AWS** | Service Quotas increase request, per region | **No free-text field exists.** Your text is seen only if AWS routes the request to a support case. |
| **Azure** | Quota API for adjustable quotas — a bare numeric limit | Carried only on a separate Microsoft Support ticket, which needs a paid support plan |
| **Google Cloud** | Cloud Quotas preference — declarative; you state the end state you want | Sent verbatim as the API's justification field |

There is no apply-everywhere call on any cloud. A fleet spanning many regions means one request
per region per quota — which is exactly the labour the agent removes.

### Realistic settlement times

Be prepared for these to differ by more than three orders of magnitude:

| Cloud | Case | Observed / documented |
|---|---|---|
| **Google Cloud** | Small delta | **Seconds.** A measured +8 preemptible vCPU request settled about 4 seconds later. |
| **Google Cloud** | Anything else | No published SLA. Approval is not guaranteed and may be **partial**; new or low-spend projects do see rejections. |
| **Azure** | Adjustable quota (vCPU families, regional total, spot pool, network counts) | **Minutes.** A measured 0 → 2 family increase in a fresh region sat in progress for about two minutes, then succeeded — with no human review. |
| **Azure** | Support-ticket path | Minutes to days, once a paid support plan exists. |
| **AWS** | Modest standard-family bump | Often auto-approved in **minutes**. |
| **AWS** | GPU families, or a large jump from zero | Usually routed to a manual support case: **hours to days.** Business/Enterprise support is faster. |

Some ceilings are frequently not raisable at all — Azure's resource-group and VM-count style
limits among them. Nothing here promises an increase before the outcome is known.

### Azure: read this before you start

**The Azure support-ticket path requires a paid support plan.** On a Free or Basic plan the API
accepts the call and then fails asynchronously with `InvalidSupportPlan` — no ticket is ever
created.

That failure is detected and reported, never hidden: you get the Azure portal's quota
blade plus the exact request text to paste in. Portal quota tickets still work on free plans.

**That branch is unvalidated, and we say so rather than implying otherwise.** Validating it would
require a paid support plan we do not hold, so no live `InvalidSupportPlan` has ever been
observed and no ticket has ever been created or refused through this API. The detection and the
portal fallback are covered by tests; the ticket API's own payload is not, and neither is the
portal blade itself. Azure's own metadata does back the one claim above it: the
`Microsoft.Support` provider exposes no plan-tier resource, so the tier really cannot be read
without attempting the write.

This affects the quotas Azure does **not** treat as adjustable. The adjustable set — regional
vCPU total, per-family vCPUs, the spot pool, and regional network counts — goes through the
Quota API and needs no support plan. Those are also the Azure quotas the engine sizes and
requests today; everything else Azure exposes is audited for visibility only.

Whether a quota is adjustable is stated on every Azure request the agent hands you, next to the
call itself — and stated as **our** classification, because Azure publishes no adjustable flag on
any of its quota APIs. So the Quota API call is still handed over even for a quota we believe it
cannot serve: Azure's own answer to it is immediate, free, and more authoritative than our guess.
A request labelled not-adjustable comes with the portal route to use when that call is refused,
and a refusal there means exactly what the label predicted — not a missing permission.

## Tracking outcomes

Nothing about a submitted request is stored. Status is re-derived live from each cloud's own API
every time you ask, keyed on `cloud/region/quota`. That survives a restart of the Advisor with
no local history to lose — and it means the answer you see is the cloud's answer, not a cached
belief about it.

Your agent holds the queue of what it submitted — the Advisor holds none of this, by design —
and polls each cloud directly with the exact call the agent's own `plan_quota_requests` handed
it. Your agent uses the same honest per-cloud reading below to tell you when something actually lands,
instead of you remembering to return to a page and press refresh.

### The status models are lossy, and differently lossy per cloud

This is the honest limitation of tracking, and it is worth knowing before you rely on a
verdict — the table below is exactly what the Advisor's own status normalizer
(`advisor/src/quota_clients/status.py`) reports, including its confidence levels, not a table this document
invented on its own:

| Cloud | What it reports | What is lost |
|---|---|---|
| **AWS** | Pending · case opened · approved · denied · not approved · **case closed** | A closed case and an explicit refusal cannot be told apart — both are reported as denied. A case can close for reasons that are not a refusal. Check the case itself. |
| **Google Cloud** | Granted value versus the value you preferred | **There is no approved/denied field.** Approved means granted ≥ preferred; a smaller non-zero grant reads as still-pending (it is not a final answer) and a zero grant as denied — a reasonable reading, not the cloud's own verdict. |
| **Azure** — adjustable | Provisioning state: accepted / in progress / succeeded / failed | Clean. Succeeded means the limit moved. |
| **Azure** — support ticket | **Open or closed only** | The Support API exposes ticket lifecycle, not a machine-readable quota outcome. A closed ticket tells you nothing about whether the quota moved. Check the portal. |

Where a verdict is inferred rather than reported, the tooling says so instead of presenting a
uniform confidence it does not have.

## The honest limits

### Region enablement is not the same as quota

A clean quota audit does **not** guarantee a region is usable.

| Cloud | Detectable? |
|---|---|
| **AWS** | **Yes.** Opt-in regions your account has not enabled are detected and reported separately, ahead of any quota gap. |
| **Azure** | **No.** Restricted-access regions expose no metadata flag, and quota reads succeed in them anyway. A deployment failure is the only reliable detector. |
| **Google Cloud** | **No.** There is no region-access-block concept to query; regions your project cannot use are simply absent from the region listing. |

No guess is invented to fill those two gaps. They are reported as gaps.

### API-rate quotas: visibility only

The token-bucket limits that govern instance create/terminate churn are read and shown, but they
get no requirement figure and no generated request. On AWS their real quota codes are not
documented and must be discovered per account rather than assumed; on Azure and Google Cloud
they are not reachable through the quota APIs the audit reads at all. Treat them as
information, and raise them
through your cloud's own console if burst churn becomes the limit you actually hit.

### When a region degrades

If a cloud throttles or denies a read, that region's limits come back unknown — and an unknown
limit is never judged, so it produces no recommendation. **A silently degraded region looks
identical to a region with nothing to do.**

Guardrails, so it does not stay silent:

- One failed cloud never drops another cloud's results; the failure is reported per cloud.
- On AWS, one denied read permission no longer wipes out a whole region's readings — limit
  reads and per-counter usage reads are isolated from each other. (This is a real incident, not
  a hypothetical: a single missing read action once wiped an entire region's limits.)
- Each affected row carries a note naming the call that failed.
- If the catalog is unreachable, the "not offered in this region" filter cannot run. The audit
  then treats every family as offered — never hiding a real gap — and says explicitly that
  the filter is off.

Your agent reads those notes and reports degradation explicitly rather than reporting an all-clear: each row's note, and the per-cloud read status beside it, travel on the same
`get_quota_report` call the agent already makes to read the audit.

### GPU comparisons are same-model only

GPU pools are priced within a model, not normalized across accelerator models. Nothing here
claims an H100 hour and an A100 hour are interchangeable.

## Where the write access lives

| Path | Credentials | Default |
|---|---|---|
| **Console** (available today) | Separate, opt-in, per-cloud write credentials in a Kubernetes Secret — distinct from the read-only credentials used by the audit | **Off.** With the feature disabled, the submission endpoint answers not-found. |
| **Agent** (available today) | **Your** cloud credentials, on **your** machine — the Advisor hands you the exact call via `plan_quota_requests`, never touches a cloud itself. | The request appears in your cloud's audit log under the identity of the person who confirmed it. |

Filing a request needs permissions the read-only audit roles do not carry — read-only viewer
access cannot submit an increase on any of these clouds. The exact permissions, with a reason
for each and instructions to revoke, live in [permissions.md](permissions.md). That document, together with the running console's "Unlock more" section, is the version-matched source of truth for the exact actions. (Those action lists are generated from the requirement catalog the clients themselves read, and a test fails the build if the document drifts from it — they are not hand-copied.)

The one thing persisted anywhere is your questionnaire answers, in a single Kubernetes
ConfigMap in the Advisor's own namespace.

## What your agent adds

Everything above is reachable by hand, through the Advisor's console. The agent removes labour,
latency and error — not capability.

| Without an agent | With an agent |
|---|---|
| Confirm a batch, then remember to come back and press refresh | The queue is held, polled, and reported — by your agent, never by the Advisor, which stores none of it |
| The submitted-request list lives in one browser profile | Your agent carries its own record, and survives a pod restart |
| One request per region per quota, by hand | Filed for you, from your machine, after your confirmation |
| A degraded region looks like a clean one | Degradation is read from the per-row notes and surfaced |
| Wait times differ wildly per cloud and you find out by waiting | Told up front which of your requests are the hours-to-days kind |

## Related

- [Getting started](getting-started.md)
- [What the agent does](what-the-agent-does.md) — scope, credentials and revocation
- [Permissions reference](permissions.md) — every permission, with a reason for each
- [Troubleshooting](troubleshooting.md)
