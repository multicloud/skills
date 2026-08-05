# Advisor permissions reference

This is the document you forward to whoever approves access. It states, per capability: the exact
permission, a reason for every action, how to grant it, what it does **not** permit, what data it
exposes and where that data goes, and how to revoke it.

Every action listed here is derived from the code that calls it. Where the current console renders
a permission the code does not actually use, this document says so rather than repeating it — an
over-broad ask costs you a review cycle, and a missing action fails at request time against a live
account.

---

## How to read this

Every capability below is **independent and optional** except the first. You can stop at any line
in this table and still get a working report; each additional grant buys a specific, named
improvement in fidelity.

| # | Capability | What it buys you | Access needed | Approved by | Status |
|---|---|---|---|---|---|
| 1 | **In-cluster read** | The report itself: what you run, what it costs, what it would cost elsewhere | Kubernetes RBAC (`get`/`list`/`watch`) | Cluster admin | Shipping |
| 2 | **Node identification** | Prices nodes whose labels don't say what they are — and nothing at all if they already do | None — no credentials of any kind | Cluster admin | Shipping, on by default — [often unnecessary; one read-only command decides](#2-node-identification-no-credentials) |
| 3 | **Utilization source** | Right-sizing against measured usage instead of declared requests | Read access to your own metrics store, if it needs auth | Whoever runs your metrics stack | Shipping |
| 4 | **Actual negotiated pricing** | Prices your baseline at your committed rates, not public list price | Read-only billing role per cloud | Cloud + billing admin | **AWS: read live and cross-checked** (2026-08-03). **Google Cloud and Azure: built and wired, never yet read against a live billing account** — treat any rate those two derive as unproven |
| 5 | **Quota visibility** | Shows the provisioning wall before you hit it | Read-only quota/usage role per cloud | Cloud admin | Shipping |
| 6 | **Quota submission** | Files increase requests from the console | **Write** role per cloud | Cloud admin | Shipping, default off — **the agent flow does not use it** |

Capability 6 exists for people driving the web console by hand. When your agent drives the flow,
quota requests are filed **from your machine with your own credentials** and no cloud write
credential is ever placed in the cluster. See [The write path](#6-quota-submission--the-write-path)
for why that is the better arrangement.

---

## 1. In-cluster read access (required)

### The guarantee

The Advisor's cluster role is **`get`, `list`, `watch` and nothing else**. It cannot read Secrets,
cannot read logs, cannot exec into a container, cannot port-forward, and holds no `create`,
`update`, `patch` or `delete` verb anywhere in the cluster.

It is deliberately short enough to audit in under a minute. Read it yourself:
`templates/rbac.yaml` in the chart.

### Exactly what it reads, and why

| API group | Resources | Verbs | Why it is needed | Used today |
|---|---|---|---|---|
| core (`""`) | `nodes` | get, list, watch | Instance type, region, capacity type and allocatable capacity — the fleet you are paying for | Yes |
| core (`""`) | `pods` | get, list, watch | Declared CPU/memory/GPU requests and which node each pod runs on — the demand to be packed | Yes |
| core (`""`) | `services` | get, list, watch | Locates an in-cluster metrics store (Prometheus, Thanos, Mimir, VictoriaMetrics, OpenObserve) by name and port | Yes |
| core (`""`) | `persistentvolumeclaims`, `persistentvolumes` | get, list, watch | Reserved for storage attribution | **No** — see note |
| `apps` | `deployments`, `statefulsets`, `daemonsets`, `replicasets` | get, list, watch | Groups pods into the workload that owns them, so the bill is attributed per workload rather than per pod | Yes |
| `batch` | `jobs`, `cronjobs` | get, list, watch | Prices CronJobs by duty cycle (run frequency × measured run duration) instead of as if they ran continuously | Yes |
| `autoscaling` | `horizontalpodautoscalers` | get, list, watch | Flags HPA-managed workloads so right-sizing defers to the autoscaler rather than fighting it | Yes |
| `policy` | `poddisruptionbudgets` | get, list, watch | Reserved for disruption-aware recommendations | **No** — see note |
| `metrics.k8s.io` | `pods` | get, list | Reads metrics-server as a weak fallback when no PromQL store is available | Yes |
| `metrics.k8s.io` | `nodes` | get, list | Reserved | **No** — see note |

**Note on the "No" rows.** Three grants in the shipped chart are not used by the current
code: `persistentvolumeclaims`/`persistentvolumes`, `poddisruptionbudgets`, and
`metrics.k8s.io/nodes`. They are read-only and low-risk, but if your reviewer works to a strict
least-privilege standard you can delete those three rules from the ClusterRole with **no loss of
function today**. If a later version needs them, the chart will ask again.

### The one write, and its blast radius

The chart grants exactly one write capability, and it is **namespaced, not cluster-wide**: a
`Role` permitting `create` on ConfigMaps in the Advisor's own namespace, plus
`get`/`update`/`patch` pinned by `resourceNames` to a single ConfigMap,
`<release>-advisor-quota-selection`.

That ConfigMap stores your own answers to the quota questionnaire (expected fleet size, regions in
scope). It is the only thing the Advisor persists anywhere.

`create` cannot be name-restricted — Kubernetes ignores `resourceNames` for `create`, because the
object name is not known at authorization time. The real bound is namespace scope: this identity
can create new ConfigMaps in its own namespace and can read or modify exactly one existing ConfigMap,
by name. It cannot touch any other ConfigMap in the cluster.

### What this grant does not permit

- Reading any Secret, anywhere.
- Reading container logs, or `exec`/`attach`/`port-forward` into any pod.
- Creating, modifying, scaling or deleting any workload.
- Any access to another namespace's ConfigMaps.
- Any node lifecycle operation — cordon, drain, delete, label.

### What data this exposes, and where it goes

It exposes your cluster's shape to a process running **inside your cluster**. Workload names,
namespace names, labels, annotations and topology are read into memory, used to build the report,
and never persisted and never transmitted.

The only outbound traffic is to the Multicloud catalog (`api.multicloud.io` by default) and it
carries an abstract resource-class query: a benchmark floor, a memory floor, a GPU class, a region
set, a price type — plus, for pricing your existing nodes, **the instance type names and region
names of nodes you already run**. No workload name, namespace, label or configuration is included
in any outbound request.

### Prerequisites your admin should know about

- `ClusterRole` and `ClusterRoleBinding` are cluster-scoped objects. If the person installing the
  Advisor cannot create them, installation fails at that step — worth checking before you start.
- The node-identification DaemonSet (capability 2) uses `hostNetwork`, which the `baseline` and
  `restricted` PodSecurity levels forbid. Before you argue that exception through, check whether
  you need the DaemonSet at all — on a fully-labelled cluster you do not, and the question never
  arises. Capability 2 has the one-command check.

### How to revoke

`helm uninstall <release>` removes the ServiceAccount, ClusterRole, ClusterRoleBinding, Role and
RoleBinding along with every other object in the release. No access survives it.

**One object does survive it**, and it is not an access grant: the quota-selection ConfigMap
above. The Advisor creates it at runtime rather than through the chart, so it carries no owner
reference and is not in the release manifest. It holds your own questionnaire answers and nothing
else, and it survives on purpose so a reinstall does not lose them. Remove it explicitly if you
want the namespace empty:

```bash
kubectl -n <namespace> delete configmap <release>-advisor-quota-selection
```

---

## 2. Node identification (no credentials)

Some clusters — self-managed nodes, custom AMIs, unusual autoscalers — carry nodes whose labels do
not say what instance type they are or whether they are spot. An unidentified node cannot be
priced, and an unpriced node quietly shrinks your savings number.

The Advisor ships a small DaemonSet that resolves this **without any cloud credentials**: each pod
reads its own node's instance metadata service and reports type, region and spot status back to
the Advisor over cluster-internal HTTP.

**Most clusters do not need it, and this is the most invasive object in the release — so decide
before you install it.** It is a fallback for node identity, not a cloud-specific requirement.
The Advisor reads instance type from the `node.kubernetes.io/instance-type` label, and
spot-versus-on-demand from `eks.amazonaws.com/capacityType`, `cloud.google.com/gke-spot` or
`kubernetes.azure.com/scalesetpriority` — **all three clouds, straight from labels**. The
DaemonSet only ever fills fields the labels left empty; a label always wins. So on a managed
cluster with a working cloud-controller-manager — EKS, GKE and AKS alike — it contributes
essentially nothing. The one thing it still contributes on a fully-labelled cluster is the **AWS
account id**, set out below.

**The check that decides it.** Read-only, needs nothing installed, and any cluster admin can run
it before approving anything:

```bash
kubectl get nodes -o custom-columns='NODE:.metadata.name,TYPE:.metadata.labels.node\.kubernetes\.io/instance-type,PROVIDER:.spec.providerID'
```

- **Every node shows a TYPE** → install with `--set introspection.enabled=false`. Nothing is
  lost, no `hostNetwork` pod ever enters your cluster, and the PodSecurity question below never
  arises. On AWS, read the account-id paragraph first — that half is a separate reason.
- **Any node shows `<none>`** → leave it on. Those nodes are exactly what it is for, and
  switching it off while they are unlabelled **drops them from the report rather than recovering
  them**. Label them yourself first (the console prints the exact command per node), and only
  then is disabling it the right move.

**The chart default is `introspection.enabled=true`, on purpose.** Someone installing the chart
directly, with neither this document nor an agent to steer them, should get full node
identification rather than a quietly degraded report. Turning it off is a decision you make from
the check above; it is not one the chart makes for you.

If you do run it, this is exactly what it is:

| Property | Value |
|---|---|
| Credentials | None. Not a cloud credential, not a Kubernetes token |
| Kubernetes API access | None — `automountServiceAccountToken: false` |
| Network | `hostNetwork: true` |
| Writes | None |
| Interval | Every 300 seconds by default (`introspection.intervalSeconds`) |

**Why `hostNetwork`.** This is about reaching a metadata service, not about which cloud you are
on: AWS's IMDSv2 hop limit — the EKS default — blocks metadata reads from inside a normal pod
network namespace, and host networking is what makes the read work at all where that applies.

**It also resolves which cloud account each node is in** — a GCP project, an Azure subscription,
or an AWS account id — because a grant request has to say which account it is for. On GCP and
Azure that comes from the providerID Kubernetes itself writes onto the Node object, not from
anything a pod reported, so treat it as verified. An AWS providerID never carries an account, so
there it comes from this same credential-free metadata read instead, over `POST /introspect` —
which, like the rest of this endpoint, is unauthenticated. An account that reached us only that
way is reported, not verified, and your agent is designed to have you confirm it before it is
printed into a grant request rather than presenting it as already checked.

**That AWS half is the one reason that survives a fully-labelled cluster**, and it is a different
reason from node identity: labels can be complete on every node and an AWS `providerID` still
names no account, so IMDS remains the only source of the account a grant request is addressed to.
Weigh it as its own question — if you are not going to file grant requests from this cluster, it
buys you nothing either, and the check above stands unchanged.

This is judged per cloud, not per node, and conservatively: a cloud is reported as verified only
when *every* account seen under it was providerID-derived. If even one node in that cloud
contributes an account some other way, the whole cloud is reported as reported-not-verified —
one unidentified node does not get to hide behind its neighbours' verified ones.

**The PodSecurity conflict — read this before you install.** `hostNetwork` is disallowed by the
`baseline` and `restricted` PodSecurity standards. If your target namespace enforces either, these
pods fail admission. That failure now degrades visibly rather than silently: the console and
`/status.json` report `introspection.silent` — enabled, and nothing ever reported — and list one
ready-to-run `kubectl label` command per affected node, so every node is recoverable without host
networking. See [troubleshooting](troubleshooting.md#the-introspection-pods-never-start).

`preflight` carries a `namespace-podsecurity-level` row for exactly this, designed as a
precondition check the Advisor runs *before* you install rather than a diagnosis after the fact. **On
this chart, it cannot actually run**: reading a namespace's label needs `get` on the
cluster-scoped `namespaces` resource, and the ClusterRole this chart installs (above) does not
grant it — widening cluster-wide RBAC to add one diagnostic sentence is a deliberate call NOT
made, and Kubernetes offers no narrower grant, because a Namespace is a cluster-scoped object.
So on this chart the row reports "could not check", the same as it would from a bare laptop with no
cluster access at all. The post-install degrade above is unaffected: it reports the symptom and
the per-node fix without reading the namespace, and only leaves PodSecurity unnamed as the cause.
**The authoritative check for this chart is the one below** — your own `kubectl`, before you
install:

```bash
kubectl get ns <namespace> -o jsonpath='{.metadata.labels}' | tr ',' '\n' | grep pod-security
```

Your options once you know the answer:

1. Install into a namespace with a `privileged` PodSecurity level (the DaemonSet still runs
   non-root with a read-only root filesystem and all capabilities dropped).
2. Label the affected nodes yourself. If you install anyway, the console names every node that
   needs it and prints the exact command for each; your agent can resolve the values from the
   cloud API using your local credentials and apply them. `introspection.enabled=false` is worth setting
   only once those nodes are identified — doing it first drops the nodes from the
   report rather than recovering them.
3. **If the node check at the top of this section already showed a TYPE on every node, none of
   this applies**: `--set introspection.enabled=false` and the PodSecurity conflict disappears
   with the DaemonSet, at no cost to the report. That is only true when the check is clean — with
   any node still unidentified, option 2 is the path and this one loses you those nodes.

**Revoke:** `--set introspection.enabled=false` on the next `helm upgrade`, or uninstall.

---

## 3. Utilization source (optional)

Right-sizing against measured usage is much better than right-sizing against declared
requests. The Advisor reads a PromQL-compatible store — it discovers one automatically by scanning
Services, or you can pin one with `metrics.endpoint`.

| What you grant | Where it goes |
|---|---|
| A read credential for **your own** metrics store — bearer token, or username/password | A Kubernetes Secret in the Advisor's namespace (`metrics.existingSecret`, or `metrics.token` / `metrics.username` / `metrics.password`) |

The credential authenticates PromQL instant queries against your store. It is never sent anywhere
else, and the store's raw responses are not transmitted out of the cluster — they are reduced to
utilization figures inside the report, which the Advisor then serves to the console and, over
`/mcp/`, to your AI agent (see
[what-the-agent-does.md](what-the-agent-does.md#what-leaves-your-cluster)).

If your store needs no auth, grant nothing — auto-discovery handles it.

**Honest limit.** Discovery works by substring-matching Service names. A store behind a
non-standard Service name, on a remapped port, or requiring a multi-tenant org header is missed,
and the Advisor silently degrades to declared requests — visible only as a muted footnote on the
report. A store that is reachable but holds no samples degrades the same way. Pin
`metrics.endpoint`, `metrics.queryPath` and `metrics.org` explicitly if you know your store is
unusual. The Advisor reports whether the store has samples, not just whether it answered: `utilization.has_data` in
`/status.json` is false when the store answered and returned no container CPU samples, and
`utilization.detail` says so — so "found but empty" is distinguishable from "found and usable"
without reading the report footnote.

**Revoke:** delete the Secret and `helm upgrade` with the metrics values unset.

---

## 4. Actual negotiated pricing — built, not yet proven

**All three clouds now have a client, and the chart wires them end to end.** `actualPricing.clouds`
and `serviceAccount.annotations` are real values, the deployment renders `ACTUAL_PRICING_CLOUDS`
from them, and the pricing engine replaces list price with the rate a client derives — per node,
per `(instance type, region, spot/on-demand)`, and never stacked on top of a stated discount.
Every action and role listed below is derived from the calls those clients actually make.

**AWS has now had its live read. Google Cloud and Azure have not.**

That distinction is not a formality, and the AWS run is the argument for why. Each client carries
assumptions no mock in this repository can test, and on AWS one of them was wrong: the very first
live call returned `400 ValidationException: And expression must have at least 2 operands` and
the entire read was dead, against a fully green test suite. Fixed, re-run, and cross-checked
against `aws ce get-cost-and-usage` to six decimal places — including two instance shapes whose
30-day window crossed a month boundary, where averaging the wrong way would have been off by 3%
and 5%. One assumption the run settled: AWS returns `us-east-1`, not `US East (N. Virginia)`.

The equivalent question for Google Cloud — whether its billing-export schema matches the query we
wrote — is still open, and so is Azure's. A wrong answer there does not error; it silently prices
part of your fleet at zero coverage. **For those two clouds, grant this only if you are willing to
treat the resulting numbers as a draft and check them against your own invoice.**

The AWS ask **narrowed** when its client landed, from three actions to one. `ce:GetDimensionValues`
enumerated dimensions that `GetCostAndUsage`'s own `GroupBy` already returns, and
`pricing:GetProducts` re-read a list price the Multicloud catalog already holds. `ec2:DescribeInstances`
and `ec2:DescribeInstanceTypes` were dropped earlier and stay dropped — nothing calls EC2 for
instance identification, because Tier 2's credential-free DaemonSet does that from Kubernetes
labels and IMDS.

Google Cloud **changed shape entirely**, and it is the one row here that asks for more than it did
before. It was `roles/billing.viewer` on the billing account. That grant buys nothing: Google
publishes no API for what you were actually *charged*. The Cloud Billing catalogue is public list
price, and the billing-account price surface returns a negotiated *rate card* — which for most
customers equals list, because GCP discounts arrive as committed-use and sustained-use **credits**
applied to usage rather than as a discounted rate. Reading it would have told a customer with a
37% committed-use discount (CUD) that they pay list price. The credit-applied amount exists only in the **BigQuery billing
export**, so that is what the client reads. `roles/compute.viewer` remains dropped.

Two consequences, stated rather than buried. This is the only pricing grant that reaches **inside
a project** — bind `dataViewer` on the export *dataset* rather than the project and it reaches the
billing-export tables and nothing else. And the export table is not discoverable from any API, so
it is configuration: set `actualPricing.gcp.exportTable`, or Google Cloud reports `unavailable` and
the baseline stays on list price.

Azure **narrowed**, and its row no longer names the built-in `Cost Management Reader`. That role
was kept deliberately for a while: a custom role was always mechanically possible —
`Microsoft.CostManagement/query/action` is a real, custom-role-eligible operation — but which
operations a working cost query needs *besides* it could not be derived from a client that did not
exist. A guessed operation list in a command you would run is worse than a built-in role whose
extra surface is disclosed.

The client exists now, and it invokes exactly that one operation. So the ask is a custom role built
from it, and the built-in role's surplus — Cost Management's whole read surface for the
subscription, plus resource-group enumeration, `Microsoft.Consumption/*/read` and
`Microsoft.Support/*/read` — is **gone rather than disclosed**. The role definition you create is
generated from the same action list this document justifies, so the two cannot disagree.

Note the extra step that comes with it: a custom role must be **created before it can be assigned**,
and creating one needs `Microsoft.Authorization/roleDefinitions/write` — Owner or User Access
Administrator, a different privilege from assigning a role. The commands below are numbered for
that reason.

### The zero-risk alternative for committed rates

If you have a known effective discount off list — an EDP, a committed-use agreement, negotiated
rate card — state it, and every baseline figure is computed net of it:

```
--set discount.mode=stated --set discount.effectiveDiscount=0.22   # 22% off list
```

The default is `list`, which is fully honest: public list price, no assumed discount.

### The grant, per cloud

Derived from each client's own endpoint and operation constants, so this table cannot drift away
from the calls the code makes. The Status column is the one thing to read twice, and the three
rows no longer say the same thing.

Note what *"Capability live"* on the AWS row does and does not claim. It means a live billing read
ran and its numbers were cross-checked. It does **not** mean the grant commands below were the
ones used: that run went through a founder identity holding broad rights, never the scoped policy
this page asks you to create. So the client is proven and the *ask* is not — which is why the row
ends "these grant commands have not yet been run as written". You are the first person to run
them; if one fails, that is worth telling us about rather than working around.

<!-- BEGIN generated:iam -->
| Cloud | Access the console currently renders | Status |
|---|---|---|
| AWS | `ce:GetCostAndUsage`, bound to the Advisor's ServiceAccount via IRSA | Capability live — these grant commands have not yet been run as written |
| Google Cloud | `roles/bigquery.jobUser` + `roles/bigquery.dataViewer`, bound via GKE Workload Identity, on the BigQuery billing-export project (jobUser) and dataset (dataViewer), not the billing account | Client shipped — never yet read against a live account, so treat any rate it derives as unproven |
| Azure | `Multicloud Advisor Pricing Reader`, bound via AKS workload identity | Client shipped — never yet read against a live account, so treat any rate it derives as unproven |

**Approved by:** billing admin — often billing-account or subscription scope

**What this buys you:** Prices what you already run at the rates you actually pay instead of public list price, so the saving quoted is your number rather than a brochure's.

**Expiry recommendation:** Review at 90 days. If it lapses, the report falls back to public list prices and says so on its face — it does not fail.
<!-- END generated:iam -->

The binding those rows describe is applied through the chart's `serviceAccount.annotations` value
and `actualPricing.clouds`, both of which the chart carries — see
[Workload identity: no key at all](#workload-identity-no-key-at-all) for the annotation per cloud.
What is proven differs per row: AWS's client has read a live billing account and its rates were
cross-checked; Google Cloud's and Azure's have not, so treat any rate those two derive as
unproven until they have.

Billing-level roles usually belong to a different person than cluster and cloud IAM. That is
precisely why this capability is requested once, alongside everything else, rather than as a
separate escalation.

---

## 5. Quota visibility (read-only)

A savings plan that assumes capacity you cannot actually provision is not a plan. This capability
audits vCPU, GPU, network and storage quotas across every region your credential can see, against
the fleet the report proposes, so a provisioning wall shows up on paper instead of at 2am.

**All reads. No writes.** Every call listed below is a `List`, `Get` or `Describe`.

### Rules the chart enforces for you

- Static credentials are **`existingSecret`-only**. There is no inline value field; a key can never
  end up in your Helm values, your release history, or your shell history.
- Enabling a cloud with **neither** a Secret nor workload identity **fails the Helm render** with a
  message naming both ways out. It cannot deploy half-configured.
- Read credentials and write credentials may **never share a Secret**. The chart refuses it, uses
  different value keys, and passes them to the container under different environment variable
  prefixes (`QUOTA_*` versus `QUOTA_REQUESTS_*`).
- Missing or partial credentials degrade that cloud to "not configured". They never crash the pod.

### Workload identity: no key at all

Everything in §5 describes **which permissions** to grant. This section is about **how the
credential reaches the pod**, and the two are independent: the action and role lists below are
identical either way, because they are derived from the same client code.

There are two deliveries. The one each per-cloud procedure walks through creates a principal and
downloads a long-lived key into a Kubernetes Secret. The other — **workload identity, and the one
we recommend** — puts no credential in your cluster at all. The pod presents the ServiceAccount
token that Kubernetes already issues it, your cloud verifies that against your cluster's OIDC issuer,
and hands back a credential that expires in minutes. Nothing to rotate, nothing to recover from an
etcd backup, and revoking the cloud-side role revokes the Advisor's access immediately rather than
whenever someone remembers the key exists.

Where your organization enforces GCP's `constraints/iam.disableServiceAccountKeyCreation`, this is
not just preferable — it is the only delivery that works, because that policy refuses the
download §5b depends on.

Two chart values turn it on. Annotate the ServiceAccount with your cloud's binding, and set that
cloud's `workloadIdentity` flag:

```yaml
serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::<account>:role/<role>          # AWS (IRSA)
    iam.gke.io/gcp-service-account: <sa>@<project>.iam.gserviceaccount.com  # Google Cloud
    azure.workload.identity/client-id: <client-id>                          # Azure

quota:
  aws:   { enabled: true, workloadIdentity: true }
  gce:   { enabled: true, workloadIdentity: true }
  azure: { enabled: true, workloadIdentity: true, subscriptionId: <subscription-guid> }
```

Both are needed. The flag alone leaves the pod with no identity to present; the annotation alone
leaves the quota reader still looking for a Secret. Set one without the other and that cloud
degrades to "not configured" naming exactly what is missing — it never reads anything under an
identity you did not choose, and it never falls back to a key you thought you had stopped using.

Three details that are easy to get wrong:

- **Azure needs a pod label as well**, `azure.workload.identity/use: "true"`. Without it AKS's
  admission webhook injects nothing and the failure mentions no label anywhere. The chart renders
  it for you whenever the Azure annotation is present, so there is nothing to set — it is listed
  here because it is the first thing to check on a hand-written manifest.
- **Azure still needs `subscriptionId`.** A quota read is scoped to one subscription and no token
  carries one. It is an identifier rather than a secret, so it goes in plain values; the render
  fails if it is missing.
- **Google Cloud takes the project from your cluster** when no key file names one. Set
  `quota.gce.projectId` only if the quotas that bound this fleet live in a different project.

The pod makes one extra call before any read: the token exchange. If you run a default-deny
egress policy, allow it — an allow-list covering only the service endpoints fails every read
with an error that looks like a bad grant.

- **AWS** calls `sts.<region>.amazonaws.com` whenever the pod carries a region, which on EKS it
  always does, and `sts.amazonaws.com` otherwise. Both are listed because which one applies is
  your cluster's choice, not ours: the global host is a us-east-1 service, so a cluster reaching
  AWS through per-region interface VPC endpoints cannot route to it, and some accounts refuse it
  outright by a Service Control Policy (SCP).
- **Azure** dials `login.microsoftonline.com` — the same host as the client-secret flow, so this
  adds no rule you do not already have.
- **Google Cloud** needs no rule at all: its token comes from the node-local metadata service and
  never crosses your network.

**Not yet exercised against a live cluster.** The code and the charts are complete and tested; no
IRSA, GKE or AKS binding has been run end-to-end here. Treat this as specified rather than proven,
like the narrow custom roles in §5b and §5c.

**The write path (§6) has no workload-identity option, deliberately.** Every container in the
Advisor pod shares one identity, so a write path delivered that way would be the *same principal*
as the read path — which is exactly the separation the read/write Secret rule above exists to
maintain. Quota submission stays a distinct principal with its own Secret.

### Blast radius shared by all clouds

The audit enumerates **every region the credential can see** and reads quotas in each. That is the
point — a quota wall in a region you have not used yet is exactly the one that surprises you — but
your reviewer should know the read covers the whole account rather than staying in one region. You can
narrow it: regions you exclude in your quota selection are skipped.

What the credential returns, and what therefore appears in the report: quota limits, current usage
counts, and region names. Not instance contents, not tags, not workload data. Multicloud receives
none of it and the report is rendered in-cluster — but the Advisor then serves that report to the
console and, over `/mcp/`, to your AI agent, so it goes wherever that agent runs (see
[what-the-agent-does.md](what-the-agent-does.md#what-leaves-your-cluster)).

---

### 5a. AWS quota read

Every action below is called by the client — this is the union `src/requirements.py` computes
from `quota_clients.aws`'s own code constants, never a hand-typed list, and a guard test in the
repository fails the build if the client ever calls an action this list omits, or if this list
asks for an action the client never calls.

<!-- BEGIN generated:iam -->
**Approved by:** cloud or security admin

**What this buys you:** Tells you where the provisioning wall is before you commit to a move: which regions can take the recommended fleet today, and which need a limit raised first.

#### Exact policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MulticloudAdvisorQuotaReadOnly",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricData",
        "ec2:DescribeAddresses",
        "ec2:DescribeEgressOnlyInternetGateways",
        "ec2:DescribeInternetGateways",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeRegions",
        "ec2:DescribeRouteTables",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVolumes",
        "ec2:DescribeVpcs",
        "servicequotas:ListAWSDefaultServiceQuotas",
        "servicequotas:ListServiceQuotas"
      ],
      "Resource": "*"
    }
  ]
}
```

#### A reason per action

| Action | Why it is needed |
|---|---|
| `cloudwatch:GetMetricData` | Reads the AWS/Usage metrics that say how much of each vCPU limit is already consumed, so headroom is measured rather than guessed. |
| `ec2:DescribeAddresses` | Counts Elastic IPs already in use against the per-region limit — the wall a node-per-region expansion usually hits first. |
| `ec2:DescribeEgressOnlyInternetGateways` | Counts egress-only internet gateways — the IPv6 path has its own separate limit, and omitting exactly this action wiped a region's limits on 2026-07-22. |
| `ec2:DescribeInternetGateways` | Counts internet gateways in the region against the per-region limit. |
| `ec2:DescribeNetworkInterfaces` | Counts network interfaces in the region; every node consumes at least one, so this limit moves with the fleet. |
| `ec2:DescribeRegions` | Lists the regions this account has enabled, so limits are only read where you could actually launch. |
| `ec2:DescribeRouteTables` | Counts route tables per VPC and routes per table, the pair a multi-region expansion runs into first. |
| `ec2:DescribeSecurityGroups` | Counts security groups and their rules — two separate limits that stop a fleet expansion well before vCPU does. |
| `ec2:DescribeSubnets` | Counts subnets per VPC so the subnets-per-VPC limit is judged against the fullest VPC you actually have, not an average. |
| `ec2:DescribeVolumes` | Sums gp3 volume size in the region so the storage-per-region limit is judged against real usage. |
| `ec2:DescribeVpcs` | Counts VPCs, and their IPv6 blocks, in the region so the VPCs-per-Region limit is judged against real usage. |
| `servicequotas:ListAWSDefaultServiceQuotas` | Reads AWS's default limit for quotas you never changed, so an untouched region reports a real ceiling instead of 'unknown'. |
| `servicequotas:ListServiceQuotas` | Reads the limit this account actually has in each region — the number every 'will the fleet fit here' answer is measured against. |

`Resource: "*"` is required because these are all account- or region-scoped describe calls with no resource ARN to constrain. Every one is read-only.

#### How to grant

```bash
aws iam create-policy --policy-name MulticloudAdvisorQuotaReadOnly --policy-document file://MulticloudAdvisorQuotaReadOnly.json   # the policy document in this request
# Preferred — the Advisor then holds no key at all. Attach to the IAM role its ServiceAccount assumes via IRSA:
aws iam attach-role-policy --role-name <ADVISOR_ROLE> --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/MulticloudAdvisorQuotaReadOnly

# Alternative — attach to the IAM user whose access keys go into the Advisor's Secret:
aws iam attach-user-policy --user-name <IAM_USER> --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/MulticloudAdvisorQuotaReadOnly
```

Then deliver the credential **one of two ways**.

*Workload identity — recommended, and the only delivery that works where long-lived keys are forbidden.* Annotate the ServiceAccount as described in [Workload identity: no key at all](#workload-identity-no-key-at-all), then:

```bash
helm upgrade <release> <chart> --reset-then-reuse-values \
  --set quota.aws.enabled=true \
  --set quota.aws.workloadIdentity=true
```

*Or a static key pair in a Secret:*

```bash
kubectl create secret generic advisor-quota-aws \
  --from-literal=AWS_ACCESS_KEY_ID=<KEY_ID> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<SECRET>

helm upgrade <release> <chart> --reset-then-reuse-values \
  --set quota.aws.enabled=true \
  --set quota.aws.existingSecret=advisor-quota-aws
```

#### What this grant does not permit

Read-only. What this Advisor **does** with it is quota-shaped: limits, usage metrics, and counts of networking and storage resources. What the grant **permits** is wider than that, and you should approve it knowing this — the counts come from EC2's `Describe*` calls, and a `Describe*` response carries the full description of every resource it covers, in every region: each security group's rules, each subnet's CIDR, each route table's routes, each network interface's addresses, each volume's attachment. That is network and storage inventory, not just its size. It still cannot read workloads, object storage, logs, or spend; it cannot create, change or delete anything; and no instance-lifecycle call is reachable with it.

**Expiry recommendation:** Review at 90 days. Nothing breaks when it lapses except the picture going blank, so a time-boxed grant costs you nothing — re-grant on demand.

#### Revoke

```bash
# Whichever principal you attached it to:
aws iam detach-role-policy --role-name <ADVISOR_ROLE> --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/MulticloudAdvisorQuotaReadOnly
aws iam detach-user-policy --user-name <IAM_USER> --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/MulticloudAdvisorQuotaReadOnly
aws iam delete-policy --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/MulticloudAdvisorQuotaReadOnly
```

Then delete the Kubernetes Secret. The Advisor degrades that cloud to "not configured" on its next audit; nothing else changes.

**Read path:** this read path has been run end-to-end against a real account.  
**Grant commands:** these exact commands have not yet been run, as written, against a real account -- treat them as drafted.
<!-- END generated:iam -->

Secret keys must be exactly `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. That is the
static-key delivery; it is not the only one.

**Workload identity (IRSA) is supported, and is the delivery we recommend** — see
[Workload identity: no key at all](#workload-identity-no-key-at-all). Attach the policy above to
the IAM role the Advisor's ServiceAccount assumes, annotate that ServiceAccount with
`eks.amazonaws.com/role-arn`, and set `quota.aws.workloadIdentity=true`. No access key is created
and there is no Secret to rotate. If your policy forbids long-lived keys, take this path rather
than skipping the capability.

---

### 5b. Google Cloud quota read

**Not `roles/compute.viewer`.** That predefined role carries Compute Engine's entire get/list
surface — instance metadata included, which is where startup scripts and SSH keys live — whereas
this reader makes three calls. It is replaced below by a custom role built from exactly those
three permissions, the same move §5c makes on Azure. `roles/cloudquotas.viewer` stays: at project
scope it is already close to minimal (`cloudquotas.quotas.get`, plus a project `get`/`list` that
a project-scoped binding barely reaches), and it is the half that has been live-read.

**Nothing but the roles below is needed for the quota read.** The GCP quota reader talks only to
`compute.googleapis.com` and `cloudquotas.googleapis.com` — never `roles/monitoring.viewer` or
any other role.

**One thing this credential dials that these roles do not cover, stated plainly.** Before the
Advisor produces a grant request it runs a preflight check against
`orgpolicy.googleapis.com` — "does this organization forbid service-account key downloads?" —
using this same service-account key, so it can warn you up front if the key the procedure below
assumes cannot be created. Neither role here carries `orgpolicy.policies.get`, and **we are not
asking you to grant it**: Google's reference for that method accepts the `cloud-platform`,
`organizationpolicy` and `organizationpolicy.readonly` OAuth scopes. This client's token is
minted `cloud-platform.read-only` (see *OAuth scope* below, which is a guarantee we would rather
keep than trade for one probe), so the permission would not make the check succeed. It reports
"could not check" and the audit continues without it. If you are writing an egress allow-list
rather than an IAM policy, allow `*.googleapis.com` rather than transcribing hostnames.

<!-- BEGIN generated:iam -->
**Approved by:** cloud or security admin

**What this buys you:** Tells you where the provisioning wall is before you commit to a move: which regions can take the recommended fleet today, and which need a limit raised first.

#### Roles, and a reason each

| Role | Why it is needed |
|---|---|
| `projects/<PROJECT>/roles/multicloud_advisor_quota_reader` | A custom role carrying only the compute reads listed below — it exists so the ask is not roles/compute.viewer, which carries Compute Engine's whole get/list surface, instance metadata included. |
| `roles/cloudquotas.viewer` | Reads the quota limits configured on your project — without it we cannot tell you where your provisioning wall is. It cannot change a limit or file a request. |

#### Exactly what it calls, and why

| Action | Why it is needed |
|---|---|
| `cloudquotas.quotas.get` | Reads the quota limits configured on your project — without it we cannot tell you where your provisioning wall is. It cannot change a limit or file a request. |
| `compute.projects.get` | Reads the project-wide quota metrics that have no region dimension (CPUs and GPUs across all regions, networks, routes). |
| `compute.regions.get` | Reads one region's quota metrics — the live usage figure that turns a configured limit into real headroom. It returns quota rows, not the resources behind them. |
| `compute.regions.list` | Lists the regions this project can use, so limits are only read where you could actually launch. It is also the first call made, and the reachability check. |

#### How to grant

```bash
# A custom role, deliberately narrower than the roles/compute.viewer this replaces:
# compute.viewer carries Compute Engine's whole get/list surface -- including instance metadata, where startup scripts and SSH keys live -- where the permissions below are all that is called.
# 1) Create the role. This needs iam.roles.create (Role Administrator, or Owner) -- a DIFFERENT privilege from setting an IAM policy binding, which is step 2:
gcloud iam roles create multicloud_advisor_quota_reader --project=<PROJECT> --title="Multicloud Advisor Quota Reader" --description="Read-only quota and usage reads for the Multicloud Advisor." --permissions=compute.projects.get,compute.regions.get,compute.regions.list --stage=GA   # creates projects/<PROJECT>/roles/multicloud_advisor_quota_reader
# 2) Bind that role, and the one predefined role above, to the Google service account the Advisor reads as -- the one bound to its Kubernetes ServiceAccount by Workload Identity, or, if you are delivering a key instead, the one whose key goes into the Advisor's Secret. The bindings are the same either way:
gcloud projects add-iam-policy-binding <PROJECT> --member="serviceAccount:<SA>@<PROJECT>.iam.gserviceaccount.com" --role="projects/<PROJECT>/roles/multicloud_advisor_quota_reader"
gcloud projects add-iam-policy-binding <PROJECT> --member="serviceAccount:<SA>@<PROJECT>.iam.gserviceaccount.com" --role="roles/cloudquotas.viewer"
```

Then deliver the credential **one of two ways**.

*Workload identity — recommended, and the only delivery that works where long-lived keys are forbidden.* Annotate the ServiceAccount as described in [Workload identity: no key at all](#workload-identity-no-key-at-all), then:

```bash
helm upgrade <release> <chart> --reset-then-reuse-values \
  --set quota.gce.enabled=true \
  --set quota.gce.workloadIdentity=true
```

*Or a static key pair in a Secret:*

```bash
kubectl create secret generic advisor-quota-gce \
  --from-file=GCE_SA_KEY_JSON=<path/to/key.json>

helm upgrade <release> <chart> --reset-then-reuse-values \
  --set quota.gce.enabled=true \
  --set quota.gce.existingSecret=advisor-quota-gce
```

#### What this grant does not permit

Read-only over quota configuration and the region and project quota metrics listed above. Nothing here can start, stop or modify a resource; nothing reaches instance metadata (the custom role replaces roles/compute.viewer precisely so that it cannot); and neither role can change a limit — the write permission cloudquotas.quotas.update, which filing an increase needs, is deliberately absent.

**Expiry recommendation:** Review at 90 days. Nothing breaks when it lapses except the picture going blank, so a time-boxed grant costs you nothing — re-grant on demand.

#### Revoke

```bash
gcloud projects remove-iam-policy-binding <PROJECT> --member="serviceAccount:<SA>@<PROJECT>.iam.gserviceaccount.com" --role="projects/<PROJECT>/roles/multicloud_advisor_quota_reader"
gcloud projects remove-iam-policy-binding <PROJECT> --member="serviceAccount:<SA>@<PROJECT>.iam.gserviceaccount.com" --role="roles/cloudquotas.viewer"
# Then the custom role itself. This is reversible -- `gcloud iam roles undelete multicloud_advisor_quota_reader --project=<PROJECT>` restores it:
gcloud iam roles delete multicloud_advisor_quota_reader --project=<PROJECT>
```

Then delete the service-account key (and ideally the service account), and delete the Kubernetes Secret.

**Read path:** this read path has been run end-to-end against a real account.  
**Grant commands:** these exact commands have not yet been run, as written, against a real account -- treat them as drafted.
<!-- END generated:iam -->

#### OAuth scope

The service account's token is issued with
`https://www.googleapis.com/auth/cloud-platform.read-only` — the read-only scope, not full
`cloud-platform`. Even if the service account were granted broader roles, this client's token
cannot authorize a write.

The Secret key must be exactly `GCE_SA_KEY_JSON`, holding the raw service-account JSON.

**Check this before you start.** Many organizations enforce the org policy
`constraints/iam.disableServiceAccountKeyCreation`, which blocks the key download this procedure
depends on. If that constraint is active in your organization, **skip this procedure and use
[workload identity](#workload-identity-no-key-at-all) instead** — it needs no downloadable key,
so the policy does not block it, and it is the delivery we would recommend even where the policy
is absent. Check first rather than
raising a ticket that will be refused. Under the agent flow, `preflight` attempts this check
automatically, before any request is produced — see
[mcp-reference.md](mcp-reference.md#plan-tools) — but **expect it to answer "could not check"
rather than yes or no**, and check it yourself anyway. The reason is above: the org-policy method
does not accept the read-only OAuth scope this credential's token is minted with, and we would
rather keep that scope guarantee than widen it for one probe. A `detected: true` from it, if you
ever see one, has also never been run against a live account — treat it as a strong signal to
verify, not a final answer.

---

### 5c. Azure quota read

**Not the built-in `Reader`.** A custom role, carrying only the operations below, replaces
subscription-wide `Reader` — the exact operation names are now specified; what remains open is
running the commands below against a real subscription (see the grant-commands line at the end of
this section).

One of those operations authorizes a call the *preflight* makes rather than the quota read:
`Microsoft.Resources/subscriptions/providers/read`, which reports whether the `Microsoft.Quota`
resource provider is registered in your subscription. It was missing from an earlier revision of
this role, and the reason the omission survived is worth knowing if you are reviewing the list: every live
read to date used the built-in `Reader` (`*/read`), which covers it, so the gap existed only in
the narrow role nobody had run yet.

<!-- BEGIN generated:iam -->
**Approved by:** cloud or security admin

**What this buys you:** Tells you where the provisioning wall is before you commit to a move: which regions can take the recommended fleet today, and which need a limit raised first.

#### Role

**`Multicloud Advisor Quota Reader`** — A custom role carrying only the reads listed below — it exists so the ask is not subscription-wide Reader, which would expose every resource you own.

#### Exactly what it calls, and why

| Action | Why it is needed |
|---|---|
| `Microsoft.Compute/locations/usages/read` | Reads each region's vCPU family limits and how much is already used — the number that decides whether the recommended fleet can exist there at all. |
| `Microsoft.Network/locations/usages/read` | Reads each region's network limits and usage — public IPs, NICs, VNets — the counts a node-per-region expansion runs into first. |
| `Microsoft.Resources/subscriptions/locations/read` | Lists the subscription's physical regions, and doubles as the reachability check; without it every later read is skipped. |
| `Microsoft.Resources/subscriptions/providers/read` | Reads whether the Microsoft.Quota resource provider is registered, so an unregistered provider is named as itself instead of looking like a denial. |
| `Microsoft.Resources/subscriptions/resourceGroups/read` | Counts resource groups in the subscription against Azure's fixed 980 ceiling, which no increase request can move. |

#### How to grant

```bash
# A custom role, deliberately narrower than the built-in Reader this replaces:
# Reader grants read on EVERY resource in the subscription, where the operations listed above are all that is called.
# 1) Create the role definition. This needs Microsoft.Authorization/roleDefinitions/write (Owner or User Access Administrator) -- a DIFFERENT privilege from assigning a role, which is step 2:
az role definition create --role-definition '{"Name":"Multicloud Advisor Quota Reader","IsCustom":true,"Description":"Read-only quota and usage reads for the Multicloud Advisor.","Actions":["Microsoft.Compute/locations/usages/read","Microsoft.Network/locations/usages/read","Microsoft.Resources/subscriptions/locations/read","Microsoft.Resources/subscriptions/providers/read","Microsoft.Resources/subscriptions/resourceGroups/read"],"NotActions":[],"DataActions":[],"NotDataActions":[],"AssignableScopes":["/subscriptions/<SUB>"]}'
# A freshly created role definition is eventually consistent -- an immediate assignment can fail with "RoleDefinitionDoesNotExist"; wait a few seconds and retry rather than assuming the definition itself failed.
# 2) Create the service principal AND assign it in one step (the CLI's --role accepts a custom role name, not only built-ins). Save appId (CLIENT_ID), password (CLIENT_SECRET) and tenant from the output -- the password is shown once and cannot be retrieved again:
az ad sp create-for-rbac --name multicloud-advisor-quota --role "Multicloud Advisor Quota Reader" --scope /subscriptions/<SUB>
# Reusing an existing app registration instead of the command above? Give it a secret, then assign the role separately. `--append` is REQUIRED here: without it, `credential reset` clears every existing password AND certificate on that app by default (installed CLI 2.86.0's own --help: 'By default, this command clears all passwords and keys') -- silently breaking every other consumer of an app registration you are, by definition, already reusing for something else:
az ad app credential reset --id <CLIENT_ID> --append
az role assignment create --assignee <CLIENT_ID> --role "Multicloud Advisor Quota Reader" --scope /subscriptions/<SUB>

# Delivering the credential by AKS workload identity instead of a client secret? The ROLE ASSIGNMENT above is unchanged -- assign the same custom role to the identity the Advisor's ServiceAccount federates to, and skip the secret entirely. The pod-side annotation, the pod label AKS keys on, and the federated-credential setup are in the Advisor's permissions document under "Workload identity: no key at all".
```

Then deliver the credential **one of two ways**.

*Workload identity — recommended, and the only delivery that works where long-lived keys are forbidden.* Annotate the ServiceAccount as described in [Workload identity: no key at all](#workload-identity-no-key-at-all), then:

```bash
helm upgrade <release> <chart> --reset-then-reuse-values \
  --set quota.azure.enabled=true \
  --set quota.azure.workloadIdentity=true \
  --set quota.azure.subscriptionId=<SUB>
```

*Or a static key pair in a Secret:*

```bash
kubectl create secret generic advisor-quota-azure \
  --from-literal=AZURE_TENANT_ID=<TENANT> \
  --from-literal=AZURE_CLIENT_ID=<CLIENT_ID> \
  --from-literal=AZURE_CLIENT_SECRET=<SECRET> \
  --from-literal=AZURE_SUBSCRIPTION_ID=<SUB>

helm upgrade <release> <chart> --reset-then-reuse-values \
  --set quota.azure.enabled=true \
  --set quota.azure.existingSecret=advisor-quota-azure
```

#### What this grant does not permit

Read-only, and confined to the usage, location and provider-registration reads listed above — narrower than the built-in Reader role, which would expose every resource in the subscription. It carries no write, no data-plane action, and no ability to change a quota.

**Expiry recommendation:** Review at 90 days. Nothing breaks when it lapses except the picture going blank, so a time-boxed grant costs you nothing — re-grant on demand.

#### Revoke

```bash
az role assignment delete --assignee <CLIENT_ID> --role "Multicloud Advisor Quota Reader" --scope /subscriptions/<SUB>
# Delete the service principal too IF it was created for this grant (step 2 above). Skip this line if you assigned the role to an app registration you already use for something else:
az ad sp delete --id <CLIENT_ID>
az role definition delete --name "Multicloud Advisor Quota Reader"
```

Then delete the Kubernetes Secret. The Advisor degrades that cloud to "not configured" on its next audit; nothing else changes.

**Read path:** this read path has been run end-to-end against a real account.  
**Grant commands:** these exact commands have not yet been run, as written, against a real account -- treat them as drafted.
<!-- END generated:iam -->

Secret keys must be exactly `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` and
`AZURE_SUBSCRIPTION_ID`. That is the static-key delivery; it is not the only one.

**Workload identity (AKS) is supported, and is the delivery we recommend** — see
[Workload identity: no key at all](#workload-identity-no-key-at-all). Assign the same custom role
to the identity the Advisor's ServiceAccount federates to, annotate that ServiceAccount with
`azure.workload.identity/client-id`, and set `quota.azure.workloadIdentity=true` alongside
`quota.azure.subscriptionId`. No client secret is created and nothing needs rotating — but the
subscription id is still required either way, because a quota read is scoped to one subscription
and no token names one.

---

## 6. Quota submission — the write path

### The agent flow does not use this

When your agent drives the flow, quota-increase requests are filed **from your machine, using your
own credentials, under your own identity**. No cloud write credential is placed in your cluster at
any point. That is a stronger position than the alternative in three ways your reviewer will care
about:

- There is no long-lived write credential sitting in a cluster for someone to find.
- Your cloud audit log shows the request under the identity of the person who confirmed it, not
  under a shared service principal.
- Revocation is the ordinary revocation of a human's access, which you already have a process for.

**If you are using the agent flow, you do not need to read the rest of this section.** Grant
nothing here.

### If you drive the console by hand

The console-only write path is unchanged, and is not being extended. It is **disabled by default**
and stays disabled unless you opt in per cloud. With the chart's defaults, on every cloud, the
Advisor performs no write anywhere, ever — and the `POST /quota/requests/submit` and
`GET /quota/requests` routes return 404, so the write path is not merely unused, it is unreachable.

If you do enable it, these remain true:

| Guarantee | Mechanism |
|---|---|
| Write credentials are separated from read credentials | Separate value keys, separate Secrets, separate container environment variables — and the chart **rejects** naming the same Secret for both, failing the Helm render rather than leaving the separation to you |
| Nothing is submitted without an explicit human confirmation | The console shows the exact cloud, region, quota and desired value for every item in the batch before anything is sent |
| No automatic submission exists | No scheduler or platform component calls these endpoints. The only caller is the console's own UI |
| Nothing is silent | Every submission and status poll is logged with the cloud-side request id or the failure reason; a partial batch failure renders per item |

### Minimum write permissions per cloud

Grant these to a principal **separate** from the read-only one above.

| Cloud | Permission | Why |
|---|---|---|
| **AWS** | `servicequotas:RequestServiceQuotaIncrease` | Submits the increase, region-scoped, absolute desired value |
| **AWS** | `servicequotas:ListRequestedServiceQuotaChangeHistoryByQuota` | Reads the outcome. This is also how status survives a pod restart — given only region and quota id, the history is re-derivable live, so no request ids are stored anywhere |
| **Azure** | `Quota Request Operator` role | The adjustable-quota path (`Microsoft.Quota` PATCH) for vCPU families, regional totals, the spot pool and network counts. `Reader` cannot submit. The `Microsoft.Quota` resource provider must be registered on the subscription — if it is not registered, affected reads fail in a way that looks like a permission problem rather than a registration one. The agent flow's `preflight` tool checks registration state before either grant request is produced, and names it as something you can register yourself (`az provider register --namespace Microsoft.Quota`) rather than a ticket |
| **Azure** | `Support Request Contributor` role | The support-ticket path, for quotas that are not adjustable through the Quota API — VM-count style ceilings and similar |
| **Google Cloud** | `cloudquotas.quotaPreferences.create` and `cloudquotas.quotaPreferences.get` | Creates the quota preference and reads its outcome. A custom role with just these two is preferable to `roles/cloudquotas.admin`, which is broader than needed |

The AWS list above is the minimum the code actually invokes. Our README additionally names
`servicequotas:GetRequestedServiceQuotaChange` and
`servicequotas:ListRequestedServiceQuotaChangeHistory`; the current code calls neither, so you can
leave them out.

The Google Cloud write path requests the full `cloud-platform` OAuth scope, because the read-only
scope cannot authorize creating a preference. That is inherent to writing, and one more reason to
keep this principal separate from the read-only one.

**Azure support-plan gate.** Ticket creation fails on Free and Basic support plans — the API
accepts the request and then reports `InvalidSupportPlan` asynchronously. The Advisor detects this
and degrades to a portal link plus the same request text rather than claiming a ticket exists. If
your subscription is on a free or basic plan, expect the ticket path to be unavailable and plan to
use the portal. There is no read-only way to learn a subscription's support-plan tier ahead of
time — the only signal is the one above, discovered by attempting the ticket itself — so the
agent flow's `preflight` tool reports this row as explicitly undetectable (rather than a false
clean bill) and names the portal fallback up front, before any attempt.

---

## Credential handling summary

| Credential | Where it lives | Written how | Revoked how |
|---|---|---|---|
| Catalog API key | Kubernetes Secret (`catalog.existingSecret`, or created by the chart) | Create the Secret yourself and pass `catalog.existingSecret`. Avoid `--set catalog.apiKey=…`: it lands in shell history and in the Helm release Secret | Self-service from your account page once self-serve signup opens — see [signup.md](signup.md). Until then, ask your Multicloud contact. Uninstalling the Advisor does **not** revoke it |
| Metrics store credential | Kubernetes Secret, optional | `metrics.existingSecret`, or inline values | Delete the Secret; rotate at your store |
| Quota **read** credential, per cloud | Kubernetes Secret, `existingSecret`-only, opt-in | You create the Secret; the chart never inlines one | Revoke the cloud role, delete the Secret |
| Quota **write** credential, per cloud | Kubernetes Secret, `existingSecret`-only, opt-in, **never the same Secret as the read one** | You create the Secret | Revoke the cloud role, delete the Secret |
| **Your** cloud credentials, under the agent flow | Your machine only | Never enter the cluster | Ordinary revocation of your own access |

---

## Network exposure

| Property | State |
|---|---|
| Inbound | `ClusterIP` Service. Reached by `kubectl port-forward` — which means **Kubernetes RBAC is the access control** |
| HTTP authentication | **None on any route**, including `/mcp/`. This is safe only because the sole access path is a port-forward |
| MCP endpoint | Mounted at `/mcp/` on the same port. **Enabled by default** (`mcp.enabled=true`). It serves your namespace and workload names to whatever agent drives it — see [what-the-agent-does.md](what-the-agent-does.md). `--set mcp.enabled=false` removes it |
| Ingress | Off by default — and while MCP is enabled, **the chart refuses to render one at all** |
| Outbound | `api.multicloud.io` (catalog), plus the cloud APIs listed above for whichever capabilities you enabled |

**Read the second and third rows together before you plan any publication.** No route
authenticates, so exposing the Advisor through an Ingress would publish both your cluster's cost
report and an unauthenticated control surface to whoever can reach that host.

The control against that is not a default, and not a promise — it is a **render-time hard
failure**. While `mcp.enabled` is true, the chart refuses to template an Ingress, or a
`service.type` outside an allowlist of `ClusterIP` and `ExternalName`. `helm upgrade` fails with
an explanatory message rather than producing a published, unauthenticated MCP endpoint. Verify it
yourself: `helm template t ./helm/advisor --set catalog.apiKey=x --set ingress.enabled=true` must
fail.

That has a consequence worth knowing before you upgrade. **A release already running
`ingress.enabled=true`, or a Service published beyond the cluster, starts failing `helm upgrade`
at the version that introduced `mcp.enabled`.** Add `--set mcp.enabled=false` and the upgrade
proceeds — you keep the console and the report and lose the agent flow. The failure is the
intended behaviour: the alternative was for a routine upgrade to silently make an
unauthenticated MCP endpoint reachable from outside the cluster.

If you need the Advisor published, that is the trade: turn MCP off and put authentication in
front of the Ingress yourself.

If your cluster egresses through a TLS-intercepting proxy, the image must be rebuilt with your CA
bundle; if it uses a `NetworkPolicy` default-deny, the Advisor pod needs egress to the catalog host.

---

## Honest limits

Things this permission set genuinely cannot do, stated plainly so you can plan around them rather
than discover them.

| Limit | Consequence |
|---|---|
| Actual negotiated pricing is proven on AWS only | All three clients ship and the chart configures them (§4). AWS has read a live account and its rates were cross-checked against the AWS CLI; Google Cloud and Azure have not. Turn AWS on and read its numbers as numbers; turn the other two on and treat every rate as a draft to check against an invoice |
| Workload identity is implemented but not yet run against a live cluster | Every read below can be delivered without a static key ([§ workload identity](#workload-identity-no-key-at-all)), and the charts render it — but no IRSA, GKE or AKS binding has been exercised end-to-end here. Treat the procedure as specified rather than proven, exactly like the narrow custom roles two rows down |
| GCP service-account key creation is often org-policy blocked | This blocks the *key* procedure (§5b), not the capability: use workload identity, which needs no key. `preflight` attempts this check before the ask, but its token's read-only scope is not one the org-policy method accepts, so it will normally report "could not check" — confirm it yourself either way |
| Azure's narrow custom role is drafted, not yet run | The role that replaces subscription-wide `Reader` is fully specified (§5c), but nobody has run `az role definition create` with it against a real subscription — the live reads to date used `Reader` |
| Google Cloud's narrow custom role is drafted, not yet run | The three-permission role that replaces `roles/compute.viewer` is fully specified (§5b), but nobody has run `gcloud iam roles create` with it against a real project — the live reads to date used `roles/compute.viewer` |
| Azure restricted regions and Google Cloud region access are undetectable | Only AWS opt-in regions can be detected programmatically. A clean quota report does not prove a region is usable. `preflight` surfaces this explicitly (`detectable: false`) rather than silently reporting no problem — it does not make the gap detectable, only visible |
| API-rate quotas are visibility only | Token-bucket quotas carry no demand attribution and their identifiers are not real quota codes; they are shown, never filed |
| Throttled reads look like quiet regions | AWS signals throttling inside 400/403 response bodies rather than 429. A degraded region reports unknown limits and produces no recommendation — which reads like "nothing to do". Check the source note on any region reporting unknowns |
| Cloud quota outcome reporting is uneven | AWS cannot distinguish a closed case from a denial; Google Cloud has no approved/denied state, only granted-versus-preferred; Azure support tickets expose only open or closed. Per-cloud confidence differs, and the report says so |
| Nothing is persisted | The report lives in memory, in a single replica. A pod restart loses it, along with the record of what was submitted in that session. Only your quota-selection ConfigMap survives |

---

## Verifying this document

Do not take any of the above on trust. Each claim is checkable against the shipped chart and image.

| Claim | How to verify |
|---|---|
| Cluster access is read-only cluster-wide | Read `templates/rbac.yaml` in the chart (`helm pull oci://registry-1.docker.io/multicloud/advisor-chart --untar`). Under a minute end to end. The ClusterRole is `get`/`list`/`watch` only; the one write grant in the file is a namespaced Role over a single ConfigMap, where the Advisor stores your own quota-questionnaire answers — `get`/`update`/`patch` pinned to it by name, plus a `create` that Kubernetes cannot name-pin, bounded by the namespace |
| Every IAM section in this document is generated, not hand-copied | `docs/external/advisor/permissions.md` is regenerated from `src/requirements.py`'s catalog by `advisor/scripts/render_permissions.py`; a test runs it with `--check` and fails the build if the committed file diverges. The same catalog also renders the setup console's IAM blocks, so the two surfaces cannot drift apart |
| The action lists are complete AND minimal, per cloud | A guard test derives the invoked-action or invoked-API set from each client's own code constants (`quota_clients.aws`'s tables, `quota_clients.gcp`'s/`quota_clients.azure`'s source) and asserts EQUALITY against the catalog cell — in both directions, so an extra action is caught as loudly as a missing one |
| Read and write credentials are kept apart | Separate value keys, separate Secrets and separate container environment variables (`QUOTA_*` versus `QUOTA_REQUESTS_*`), and the chart refuses to render if you name the same Secret for both. Check it: `helm template t ./helm/advisor --set catalog.apiKey=x --set quota.aws.enabled=true --set quota.aws.existingSecret=same --set quotaRequests.aws.enabled=true --set quotaRequests.aws.existingSecret=same` must fail. Two *different* Secrets holding the same underlying cloud principal is still yours to avoid — the chart cannot see that |
| The write path is unreachable by default | With default values, `POST /quota/requests/submit` returns 404 |
| Nothing about your workloads reaches Multicloud | Watch the pod's egress: `api.multicloud.io` always, plus your own cloud's API endpoints for whichever capabilities you enabled. What reaches the catalog is resource-class queries plus your nodes' instance-type and region names |
| What your own AI agent is served, and therefore what reaches its model | A different question, and egress-watching cannot answer it — `/mcp/` is an inbound pull over your port-forward. Have your agent call `get_workloads` and show you the raw result: your namespaces and workload names are in it, and `get_report(detail="full")` returns the whole report. Anything it reads goes wherever that agent runs, which may be a hosted model. `--set mcp.enabled=false` removes the endpoint |
| No cloud write tool exists in the agent surface | List the MCP server's tools (15 today: 5 read, 7 plan including `plan_grant_requests`, 3 act). There is no submit tool, no cloud-write tool, and no tool that accepts a credential |
| The MCP endpoint cannot be published by accident | It is a render-time failure, not a default you could override. `helm template t ./helm/advisor --set catalog.apiKey=x --set ingress.enabled=true` must fail, and so must `--set service.type=LoadBalancer`. `service.type` is an allowlist (`ClusterIP`, `ExternalName`), so a value differing only in case or trailing whitespace is refused rather than guessed at |

---

## Related

- [Getting started](getting-started.md) — the happy path, end to end
- [What the agent does](what-the-agent-does.md) — scope, blast radius, data handling
- [Manual install](manual-install.md) — the same outcome with no agent at all
- [Quota](quota.md) — what gets requested, per-cloud lifecycle, realistic wait times
