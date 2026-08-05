# Installing the Advisor by hand

The agent is a shortcut, never a dependency. Every capability the Advisor has is reachable
with `kubectl`, `helm` and a browser — this document is the whole path, in order, including the
parts that are currently rough.

You will end up with: a read-only pod in your cluster, a console on `localhost`, and a savings
report you can export as HTML, JSON or PDF.

---

## What you need before you start

| You need | Why | Who usually holds it |
|---|---|---|
| `kubectl` against the target cluster | Everything below | You |
| Helm 3.14 or newer | OCI chart distribution needs 3.8; the `helm upgrade` snippets below use `--reset-then-reuse-values`, added in 3.14 | You |
| Rights to create `ClusterRole` + `ClusterRoleBinding` | The Advisor lists nodes and workloads cluster-wide | Often a separate approval — both objects are cluster-scoped |
| Rights to create a namespace, `ServiceAccount`, `Deployment`, `Service`, `Secret`, `Role`, `RoleBinding` | The chart's objects | You, in your own namespace |
| Rights to create a `DaemonSet`, in a namespace whose PodSecurity level permits `hostNetwork` | **Only if you keep node introspection on** (Tier 2), which most clusters do not need. Run [the one check in Step 2](#decide-node-introspection-before-you-install) before you ask anyone for this | Cluster admin — see [Tier 2](#tier-2--node-introspection) |
| Pod egress to `https://api.multicloud.io` | The only outbound call the Advisor makes | Network / security |
| A catalog access key | Authenticates that one outbound call | Your Multicloud contact — see [Step 1](#step-1--get-a-catalog-key) |

Optional, and only if you want the corresponding capability:

| Also needed | Unlocks |
|---|---|
| A read-only quota role in each cloud account you provision into | Tier 4 — quota visibility |
| Credentials for an in-cluster PromQL store | Usage-driven right-sizing |

**Egress caveat.** The pod talks to the catalog over HTTPS with the image's bundled trust store. If
your egress path terminates and re-signs TLS with a private CA, point `catalog.caBundle.existingConfigMap`
at a ConfigMap holding a **full** CA bundle — the chart mounts it read-only and names it in
`SSL_CERT_FILE`. Shipped in 0.5.0; the bundle must be complete, because `SSL_CERT_FILE` replaces
the default trust store rather than adding to it. See [Egress proxies and TLS
interception](#egress-proxies-and-tls-interception). (The `PIP_CA` argument in the Advisor's build
script is a *build-time* trust setting for installing Python packages — it does not affect runtime
calls, and does not help here.)

---

## Step 1 — Get a catalog key

The Advisor prices your fleet against the Multicloud catalog. Every query it sends is abstract —
a benchmark floor, a memory floor, a GPU class, a region set. No workload name, namespace, label
or Secret reaches Multicloud.

(That is a statement about what the Advisor *sends*. What it *serves* is a separate question:
this chart enables the MCP endpoint by default, and anything an AI agent reads through it goes
wherever that agent runs. On this manual path nothing is driving it, and `--set mcp.enabled=false`
switches it off outright — see
[what-the-agent-does.md](what-the-agent-does.md#what-leaves-your-cluster).)

That query is authenticated with a scoped, revocable key.

**See [signup.md](signup.md)** for the full account, organization and key-creation flow,
including how to mint, rename and revoke a key yourself once you have an account. Self-serve
signup is not open yet — until it is, the key is created for you separately by your Multicloud
contact and sent once; store it like any other secret.

Keep the value out of your shell history and out of Helm values, both of which store it:

```bash
kubectl create namespace advisor

read -rs CATALOG_API_KEY        # paste the key; it is not echoed
printf %s "$CATALOG_API_KEY" | kubectl -n advisor create secret generic advisor-catalog \
  --from-file=CATALOG_API_KEY=/dev/stdin
unset CATALOG_API_KEY
```

`printf %s` matters: a trailing newline becomes part of the header value and the catalog call
fails. The Secret key name must be exactly `CATALOG_API_KEY`.

---

## Step 2 — Install the chart

The chart and the container image are both public — no registry login is needed for either.
Every command below also works with a local chart directory or `.tgz` in place of the OCI URL.

Pass `--version` explicitly. The setup console renders the version it believes it is running, and
if you want to check what is actually published:

```bash
helm show chart oci://registry-1.docker.io/multicloud/advisor-chart --version <version>
```

### Decide node introspection before you install

The chart's most invasive object is on by default, and most clusters do not need it. Decide this
now rather than after your security reviewer asks.

`introspection.enabled=true` installs a `hostNetwork` DaemonSet that lands on **every** node,
tainted and control-plane nodes included, and re-reads each node's instance metadata every
5 minutes for the life of the release. It is a **fallback for node identity, not a cloud-specific
requirement** — it fills only the fields your node labels do not already carry, and a label always
wins over it. Instance type comes from `node.kubernetes.io/instance-type`, and spot-vs-on-demand
from one of four vendor labels covering AWS, Google Cloud and Azure alike, so on a managed cluster
with a working cloud-controller-manager — EKS, GKE and AKS equally — the DaemonSet contributes
essentially nothing.

One read-only check settles it. It needs nothing installed and no rights beyond the `get nodes`
you already used:

```bash
kubectl get nodes -o custom-columns='NODE:.metadata.name,TYPE:.metadata.labels.node\.kubernetes\.io/instance-type,PROVIDER:.spec.providerID'
```

| What you see | What it means | What to install |
|---|---|---|
| **Every node shows a TYPE** | Your labels already identify the fleet | `--set introspection.enabled=false`. Nothing is lost |
| **Any node shows `<none>`** | Self-managed, kubeadm, or no cloud-controller-manager — exactly what the DaemonSet is for | Keep it on. Turning it off drops those nodes from the priced fleet entirely |

**On AWS there is a second reason, and it survives even when every label is present.** An AWS
`providerID` is `aws:///<zone>/<instance-id>` and names no account, while a Google Cloud or Azure
`providerID` carries the project or the subscription in the `PROVIDER` column above. So on AWS the
DaemonSet's credential-free metadata read is the only source of the account number that a
**quota-increase grant request** (Tier 4, `/quota`) is addressed to — and the Advisor still marks
that account self-reported, never verified, because `POST /introspect` is cluster-internal and
unauthenticated. If you will not be filing grant requests, this reason does not apply to you
either.

**One thing the check does not cover.** It proves the instance type is labelled — not the region
and not the capacity type, both of which a node also needs before the Advisor will price it. In
practice a cluster that labels the type labels the region too (the same cloud-controller-manager
writes both), so the one that actually bites is capacity: a node the Advisor can type but cannot
call spot-or-on-demand stays unpriceable. GKE in particular labels `cloud.google.com/gke-spot` on
spot nodes and often nothing on the rest. So if you install with introspection off, read the
console's **Spot unknown** column at
[Step 4](#step-4--read-the-readiness-console): if it is empty you are done, and if it is not,
either label those nodes ([Tier 1](#tier-1--node-labels)) or turn introspection back on
([Tier 2](#tier-2--node-introspection)). Both commands are below.

Install with the answer your check gave. Every node had a TYPE — the common case on EKS, GKE
and AKS:

```bash
helm install audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor \
  --set catalog.existingSecret=advisor-catalog \
  --set introspection.enabled=false
```

Some node showed `<none>`, or you are on AWS and want the account id for grant requests:

```bash
helm install audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor \
  --set catalog.existingSecret=advisor-catalog
```

The chart version and the image tag always match; the two move together. Objects are named after the release:
release `audit` gives you `audit-advisor` (Deployment, Service, ServiceAccount, ClusterRole,
ClusterRoleBinding), plus `audit-advisor-introspect` (DaemonSet) only when introspection is on.

Useful install-time values:

| Value | Default | Effect |
|---|---|---|
| `catalog.existingSecret` | `""` | Name of a Secret holding `CATALOG_API_KEY`. Preferred. |
| `catalog.apiKey` | `""` | Inline alternative. The render **fails** unless one of these two is set. Avoid — it ends up in your shell history and in the Helm release Secret. |
| `catalog.caBundle.existingConfigMap` | `""` | Behind a TLS-intercepting egress proxy: a ConfigMap holding a **full** CA bundle, mounted and named in `SSL_CERT_FILE`. See [Egress proxies](#egress-proxies-and-tls-interception). |
| `catalog.caBundle.key` | `ca-bundle.crt` | The key within that ConfigMap. |
| `discount.mode` / `discount.effectiveDiscount` | `list` / `0` | Set `stated` + a rate (e.g. `0.22`) to price your current bill at your negotiated discount rather than public list. |
| `cloudAllowlist` | `""` | Comma-separated clouds the report may recommend, e.g. `aws,gce`. Empty means every cloud. |
| `regionAllowlist` | `""` | Regex passed to the catalog's region filter. Limits every cross-region move. |
| `introspection.enabled` | `true` | The `hostNetwork` node-introspection DaemonSet, on every node. On by default so that a direct chart install identifies nodes fully rather than degrading in silence — but set it `false` if [the check above](#decide-node-introspection-before-you-install) showed every node already labelled. See Tier 2. |
| `pdf.enabled` | `true` | Server-side PDF export. |
| `ingress.enabled` | `false` | See Step 3 before you turn this on. Requires `mcp.enabled=false` — the render fails otherwise. |
| `service.type` | `ClusterIP` | An allowlist while MCP is enabled: only `ClusterIP` and `ExternalName` are accepted. Anything else publishes the whole Service and likewise requires `mcp.enabled=false`. |
| `mcp.enabled` | `true` | The in-cluster MCP server, mounted at `/mcp/` on the same port as the console and reached over the same port-forward. Cannot be combined with anything that publishes the Service — `ingress.enabled`, or a `service.type` outside `ClusterIP`/`ExternalName` (see Step 3). Must be a real boolean, not a quoted string. |

That table is a selection. The full, commented list is the chart's own `values.yaml`:

```bash
helm show values oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0
```

What now *enforces* it is `values.schema.json`, which ships inside the chart — read it with
`helm pull oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 --untar`.

**A misspelled value now fails the install instead of being ignored.** Every earlier release
accepted any key you cared to type and dropped the ones it did not recognise, so setting
`actualPricing.cloud` — singular, for `actualPricing.clouds` — installed cleanly and did nothing
at all. The chart now refuses it:

```
Error: values don't meet the specifications of the schema(s) in the following chart(s):
advisor-chart:
- at '/actualPricing': additional properties 'cloud' not allowed
```

This is a **breaking change on upgrade** if a values file you already keep under source control
carries a stray key. That is the intended outcome — the key was doing nothing before — but it
surfaces at `helm upgrade`, so run one with `--dry-run` first if your values file has been around
a while.

Four maps stay deliberately open, because their vocabulary belongs to somebody else:
`serviceAccount.annotations` and `ingress.annotations` (each cloud and each ingress controller
uses its own names), and `resources` / `introspection.resources` (Kubernetes' own, where
`ephemeral-storage`, `hugepages-*` and extended resources such as `nvidia.com/gpu` are all
legitimate). Anything you set under those four is passed through untouched.

### What the install actually grants

The RBAC is deliberately short enough to read in full before you approve it:

| Scope | Resources | Verbs |
|---|---|---|
| Cluster | nodes, pods, services, persistentvolumeclaims, persistentvolumes | get, list, watch |
| Cluster | deployments, statefulsets, daemonsets, replicasets | get, list, watch |
| Cluster | jobs, cronjobs | get, list, watch |
| Cluster | horizontalpodautoscalers, poddisruptionbudgets | get, list, watch |
| Cluster | `metrics.k8s.io` pods and nodes | get, list |
| Namespace | one ConfigMap, `audit-advisor-quota-selection` | get, update, patch (plus `create`, which Kubernetes cannot restrict to a single object name, in this namespace only) |

Absent by design: Secrets, ConfigMap contents beyond that one object, pod logs, exec, attach,
port-forward, and every write verb outside that single ConfigMap. The pod runs non-root
(uid 65532), with a read-only root filesystem, no privilege escalation and all capabilities
dropped. The first three are chart defaults under `securityContext` and you can change them;
the capability drop is not one — `securityContext.capabilities.drop` accepts only `["ALL"]`,
and the render fails with the reason if you set anything else. Nothing here needs a Linux
capability, and the drop is what makes the pod allowed under PodSecurity `restricted`.

Verify:

```bash
kubectl -n advisor rollout status deploy/audit-advisor
kubectl -n advisor get pods -l app.kubernetes.io/name=advisor
```

---

## Step 3 — Reach the console

The default access path is a port-forward, which means **Kubernetes RBAC is the gate**:

```bash
kubectl -n advisor port-forward svc/audit-advisor 8080:8080
open http://localhost:8080/
```

> **The Advisor has no authentication on any HTTP route.** That is safe behind a port-forward,
> because reaching it requires port-forward rights on the namespace. It is *not* safe behind an
> Ingress. `ingress.enabled=true` publishes the console, the full report, the quota page and the
> node-introspection ingest endpoint with no login of any kind, and the chart adds no
> authentication annotations for you. If you enable Ingress, put your own authenticating proxy in
> front of it and restrict who can reach the host.

The same port-forward also carries the MCP server at `http://127.0.0.1:8080/mcp/`, which is how
an AI agent drives the Advisor. See the [MCP reference](mcp-reference.md).

> **Publishing the Service and MCP are mutually exclusive, and the chart enforces it.** Both
> `ingress.enabled=true` and any `service.type` outside `ClusterIP`/`ExternalName` publish the whole
> Service — port 8080, every route, `/mcp/` along with everything else — and there is no
> way to route one path differently and exclude it. Any of the three therefore requires
> `mcp.enabled=false`; otherwise `helm install`/`helm upgrade` **fails**, naming which one
> caused it and the fix.
>
> `mcp.enabled` must also be a real boolean: `--set-string mcp.enabled=false` is rejected,
> because the pod reads a quoted `"false"` as *enabled* and would leave the server running
> while your values file said otherwise. Unset, `null` or empty means the default.
>
> **This is a breaking change for an existing install.** A release already running
> `ingress.enabled=true`, or a Service published beyond the cluster, will start failing
> `helm upgrade` at the version that introduced `mcp.enabled` (which defaults to `true`). Add
> `--set mcp.enabled=false`, or set it in your values file, and the upgrade proceeds. The
> failure is deliberate: the alternative was for a routine upgrade to make an unauthenticated
> MCP endpoint reachable from outside the cluster in silence.

---

## Step 4 — Read the readiness console

`GET /` is the setup and status console; `GET /status.json` is the same assessment as JSON. They
do **not** cost the same.

`GET /` always forces a fresh assessment — a full cluster collect, a live catalog probe, metrics
discovery and a probe of every configured quota cloud — because a person pressing reload expects
fresh. That takes a few seconds and is not something to poll.

`GET /status.json` reads a cache. The assessment is computed once and invalidated on the events
that actually change it (a newly-reporting node, `POST /refresh`, a discount change, a quota
rebuild), plus a 30-second TTL backstop for what none of those catches — mainly a credential
Secret rotated under the pod. Every response carries `fresh_as_of` and `age_seconds`, so you can
tell a 30-second-old answer from a fresh one instead of guessing. **This is the endpoint to poll**;
the console is not.

**The headline badge.**

| Badge | Means |
|---|---|
| Ready — full coverage | The catalog answers, and *every* node is fully identified |
| Partial | Some nodes are identified, some are not. The report covers the ones that are |
| Not ready | The catalog is unreachable or unauthenticated, nodes are not listable, or no node is identified at all |

A node counts as identified only when **instance type, region and spot-vs-on-demand** are all
known. All three matter: pricing a spot node as on-demand invents roughly threefold savings,
so the Advisor refuses to price a node whose capacity type it cannot resolve.

**Be aware of what "ready" does not promise.** It verifies identification, not that every
identified node's SKU is priceable in the catalog. A green badge with an empty or implausible
report means you should read the report's own data-gap notes rather than trust the badge. This is
a known over-promise and is tracked as such.

**Coverage by cloud** breaks the same numbers down per cloud, with two failure columns: *No type*
(no instance type from labels or introspection) and *Spot unknown* (type and region known,
capacity type unresolved). Those two columns are the work list for Tier 1 and Tier 2 below.

**Pricing basis** reports `list`, `mixed` or `actual`. See [Tier 3](#tier-3--actual-negotiated-pricing)
before you plan around `actual`.

**Utilization source** grades the input to right-sizing:

| Source | Quality | What you get |
|---|---|---|
| PromQL store with container CPU samples | strong | Steady (p95) and peak usage — real right-sizing |
| metrics-server only | weak | An instantaneous reading, no history |
| Declared requests | none | Right-sizing falls back to what workloads asked for, which understates savings on over-provisioned pods |

If the Advisor found a store but it answered without container CPU data, the console says so
explicitly ("reachable but no container CPU samples") rather than quietly degrading. Read that
line — "found but empty" and "not found" have different fixes.

The cross-cloud headline never depends on metrics. Only the right-sizing lever (one of the report's on/off controls — see Step 7) does.

---

## Step 5 — Unlock each tier by hand

Each tier is independent and optional. Apply a change, then re-validate.

> **Two rules that will cost you an afternoon if you skip them.**
>
> 1. **Choose a credential delivery before you enable a quota cloud.** Setting
>    `quota.<cloud>.enabled=true` with neither `quota.<cloud>.existingSecret` nor
>    `quota.<cloud>.workloadIdentity=true` makes the Helm render **hard-fail** — not the pod, the
>    whole release. `quotaRequests.<cloud>.*` still requires a Secret and has no workload-identity
>    option, deliberately: every container in the pod shares one identity, so a write path
>    delivered that way would be the same principal as the read path. Typing
>    `quotaRequests.<cloud>.workloadIdentity=true` anyway is refused by the chart schema — there
>    is no such key — rather than accepted and ignored as it was before 0.4.x.
> 2. **`--reuse-values` silently drops values introduced by a newer chart version.** That is why
>    every snippet here and in the console uses `--reset-then-reuse-values` instead. If you reach
>    for `--reuse-values` out of habit while upgrading across chart versions, don't — or keep a
>    values file under source control and pass `-f`.

### Tier 1 — node labels

Read automatically, no setup, present by default on managed clusters. The Advisor reads
`node.kubernetes.io/instance-type` (or the `beta.` form), `topology.kubernetes.io/region`, and one
of four vendor capacity labels:

`karpenter.sh/capacity-type` · `eks.amazonaws.com/capacityType` · `cloud.google.com/gke-spot` ·
`kubernetes.azure.com/scalesetpriority`

Anything else — a self-managed node pool, a custom autoscaler, your own label convention — leaves
the capacity type unknown and the node unpriceable. There is no provider-ID fallback today.

If you know the answer, you can just say so:

```bash
kubectl label node <node> karpenter.sh/capacity-type=spot        # or on-demand
kubectl label node <node> node.kubernetes.io/instance-type=<type>
kubectl label node <node> topology.kubernetes.io/region=<region>
```

Accepted capacity values are `spot` / `true` and `on-demand` / `on_demand` / `ondemand` /
`regular` / `false` — the last one because `cloud.google.com/gke-spot=false` is the only way to
say *on-demand* in that label's own vocabulary, and GKE usually writes nothing at all on a
non-spot node. **Labels win over introspection** — the Advisor only fills gaps, it never overrides a
label you set. A wrong label produces a wrong report silently, so set them only where you are
sure.

### Tier 2 — node introspection

On by default, and **a fallback for what Tier 1 could not identify — not something any particular
cloud requires.** If [the check in Step 2](#decide-node-introspection-before-you-install) showed a
type on every node, you installed with `introspection.enabled=false` and this whole tier is
already behind you; skip to Tier 3.

One credential-free pod per node reads the node's own instance metadata service and reports type,
region and capacity type back to the Advisor, filling exactly the gaps Tier 1 leaves — and only
those gaps, because a label always wins. It mounts no ServiceAccount token, holds no cloud
credentials, and writes nothing.

What it does cost you, while it is on: the DaemonSet tolerates every taint, so it lands on
**every** node including control-plane ones, and each pod re-reads metadata every 5 minutes for as
long as the release exists.

It uses `hostNetwork`, because that is what keeps the metadata service reachable when the pod
network cannot reach it — an EKS IMDSv2 hop limit is the common case, and a network policy or a
metadata proxy can block the same call elsewhere. That is also what makes it incompatible with the
`baseline` and `restricted` PodSecurity standards: in such a namespace the DaemonSet pods fail
admission.

That rejection is reported, not silent. The chart tells the pod introspection was enabled, so
`GET /status.json` distinguishes "enabled and nothing ever arrived" (`introspection.silent`) from
"never installed", and `unidentified_nodes[].label_commands` carries one ready-to-run `kubectl
label` per affected node. Run the Advisor in a namespace that permits `hostNetwork`, or label the
listed nodes — and only once they are identified, turn introspection off. Turning it off first
drops those nodes from the report rather than recovering them:

```bash
helm upgrade audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor --reset-then-reuse-values --set introspection.enabled=false
```

And the other direction — you installed with it off, and the console then showed nodes under
*No type* or *Spot unknown* that you would rather not label by hand:

```bash
helm upgrade audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor --reset-then-reuse-values --set introspection.enabled=true
```

That upgrade adds the DaemonSet, so it needs the `DaemonSet` create right and a namespace whose
PodSecurity level permits `hostNetwork`. Use a real boolean either way: the 0.5.0 schema types
this value, so `--set-string introspection.enabled=false` is refused outright rather than leaving
a quoted string behind that plain Helm truthiness would read as *on* — which is precisely the
restricted-PodSecurity cluster where turning it off was the remedy.

Two timing facts worth knowing:

- Nodes appear identified up to **5 minutes** after install (`introspection.intervalSeconds`,
  default `300`), and again after every Advisor pod restart. A blank coverage table one minute in
  is normal.
- The introspection map is held **in memory only**. An Advisor restart loses it until each node
  re-reports. When a new node does report, the cached report is invalidated and rebuilt, so the
  numbers self-heal rather than staying stale.

### Tier 3 — actual negotiated pricing

**All three clouds have clients now. AWS has been read against a live account; Google Cloud and
Azure have not.** That difference is the one that should govern your decision.

| Cloud | Reads | Grant |
|---|---|---|
| AWS | Cost Explorer, on-demand and spot separately | One action: `ce:GetCostAndUsage` |
| Google Cloud | Your BigQuery billing export, committed-use credits applied | Two BigQuery roles, on the export project and dataset |
| Azure | Cost Management `ActualCost`, grouped by meter and location | A one-operation custom role you create |

Every rate Google Cloud or Azure derives is **unverified against a real account**. AWS's rates have been verified against a real account —
a live read ran and its rates were cross-checked against a hand-run
`aws ce get-cost-and-usage` to six decimal places. The maturity is recorded per table cell rather than in
this paragraph: [permissions.md](permissions.md) prints it beside each cloud's grant.

The chart plumbing works: `actualPricing.clouds` and `serviceAccount.annotations` reach the pod.
In earlier releases they were accepted by Helm and discarded — and nothing said so,
which is how this went unnoticed for months. The chart now carries a `values.schema.json` that
refuses an unknown key outright, so that particular silence cannot recur.

**Google Cloud needs one more value**, and it is not optional. Google publishes no API for what
you were actually *charged* — the amounts with committed-use and sustained-use credits applied
exist only in the BigQuery billing export, and nothing in the API says which table that is:

```bash
--set actualPricing.clouds="{gce}" \
--set actualPricing.gcp.exportTable=<EXPORT_PROJECT>.<DATASET>.<TABLE>
```

Leave it unset and Google Cloud reports `unavailable` with that reason rather than guessing.

**Google Cloud is also the only cloud whose read costs you money**: it is a BigQuery query
against your own export, and BigQuery bills by bytes scanned. Every query the Advisor sends
carries `maximumBytesBilled`, so BigQuery refuses one that would scan past the ceiling instead
of running it and invoicing you. The default is 100 GiB, and a cloud that hits it degrades to
list price naming this value rather than appearing on your bill:

```bash
--set actualPricing.gcp.maxBytesBilled=214748364800
```

**And one Google-specific caveat about identity.** The GCE metadata server answers a token
request whether or not Workload Identity is bound — without it, with the *node's* own service
account, and nothing in the response distinguishes the two. So the Advisor compares the
identity the metadata server reports against the `iam.gke.io/gcp-service-account` annotation
you set, and refuses to read when they differ, rather than auditing your bill under an identity
you never granted. Set no annotation and there is nothing to compare, so the check is skipped:
on a self-managed cluster whose node service account is the one you meant, that is correct — but
it is then a choice you are making rather than a check you are getting.

Whatever a cloud cannot price falls back to list, and the report says so plainly — data gap
`G8`, carrying the per-cloud reason, so `unsupported` (wait for a release) is never confused with
`unavailable` (fix a grant).

**Our advice while Google Cloud and Azure stay unverified:** treat their Tier 3 figures as
a rough guide, and keep the stated-discount baseline below as the number you take to finance. A rate
derived from a query no one has ever run against a real bill is not yet evidence.

The stated-discount route, which needs no grant at all:

```bash
helm upgrade audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor --reset-then-reuse-values \
  --set discount.mode=stated --set discount.effectiveDiscount=0.22
```

This applies your rate to your current bill and to on-demand candidate fleets, and not to spot
prices (the catalog already returns real spot rates). It generally narrows the headline saving —
which is the point. A number your finance team can reproduce is worth more than a bigger one they
cannot.

### Tier 4 — quota visibility

A read-only quota and usage role per cloud, so the Advisor can audit vCPU, GPU, network and
storage limits against the fleet it recommends — and you find the provisioning wall before you
commit to a move rather than after.

Two ways to deliver the credential, per cloud. **Prefer the first.**

**Workload identity — no credential in the cluster at all.** The pod presents the ServiceAccount
token Kubernetes already issues it and your cloud exchanges it for something short-lived. Nothing
to rotate, and revoking the cloud-side role revokes access immediately. It is also the only option
under GCP's `constraints/iam.disableServiceAccountKeyCreation`, which refuses the key download the
other path needs.

```bash
helm upgrade audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor --reset-then-reuse-values \
  --set 'serviceAccount.annotations.eks\.amazonaws\.com/role-arn=arn:aws:iam::<ACCOUNT>:role/<ROLE>' \
  --set quota.aws.enabled=true --set quota.aws.workloadIdentity=true
```

Both the single quotes and the escaped dots matter. Helm splits an unescaped dot into a new key,
and it does **not** strip double quotes from a key segment — so the `--set a."b.c"=v` form you may
have seen elsewhere produces the literal key `"b.c"`, quotes included. Either mistake renders
cleanly and creates an annotation no cloud will ever match.

Per cloud, the annotation is `iam.gke.io/gcp-service-account` (Google Cloud) or
`azure.workload.identity/client-id` (Azure). Azure additionally needs
`--set quota.azure.subscriptionId=<GUID>` — a quota read is scoped to one subscription and no
token carries one; the render fails if it is missing. Set the flag without the annotation and that
cloud degrades to "not configured" naming what is absent, rather than reading under an identity
you did not choose.

**A static key.** Credentials are **existingSecret-only** — nothing is ever inlined in Helm
values. Create the Secret first, then enable the cloud:

| Cloud | Secret keys |
|---|---|
| AWS | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Azure | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_SUBSCRIPTION_ID` |
| Google Cloud | `GCE_SA_KEY_JSON` (the raw service-account key file) |

```bash
kubectl -n advisor create secret generic advisor-quota-aws \
  --from-literal=AWS_ACCESS_KEY_ID=<KEY_ID> --from-literal=AWS_SECRET_ACCESS_KEY=<SECRET>

helm upgrade audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor --reset-then-reuse-values \
  --set quota.aws.enabled=true --set quota.aws.existingSecret=advisor-quota-aws
```

The same shape applies per cloud (`quota.azure.*`, `quota.gce.*`), and each cloud is independent:
missing or partial credentials degrade that cloud to "not configured" and never block the pod
from starting. Enabling a cloud with **neither** delivery fails the Helm render, naming both.

**For the exact permissions to grant, use the console's own "Unlock more" section** rather than
any document, including this one. The console is version-matched to the Advisor you are running;
a copied list in a document drifts, and a drifted list has already caused one live incident where
a single missing read action wiped an entire region's limits from an audit.
[permissions.md](permissions.md) carries the reviewed, per-action rationale you can forward to a
security admin.

The Advisor never writes to a cloud with these credentials. There is one separate, explicitly
opt-in write path — quota-increase submission from the `/quota` page — which uses different Helm
values (`quotaRequests.*`), different Secrets and different environment variables, and is off by
default. Its submit and status routes return 404 until you configure write credentials for at
least one cloud. See [quota.md](quota.md).

---

### Egress proxies and TLS interception

If your cluster's egress goes through a proxy that terminates and re-issues TLS, the Advisor's
own calls to the catalog fail certificate verification — the pod does not know your proxy's CA.

The `PIP_CA` build secret does **not** solve this. It exists so `uv`/`pip` can fetch dependencies
while the image is *being built*, and it deliberately leaves no trace in the image, so it
installs nothing for the running pod.

Supply the CA to the pod instead:

```bash
# SSL_CERT_FILE replaces the trust store rather than adding to it, so build a FULL bundle
cat /etc/ssl/certs/ca-certificates.crt corp-root.crt > ca-bundle.crt
kubectl -n advisor create configmap corp-ca --from-file=ca-bundle.crt
helm upgrade advisor oci://registry-1.docker.io/multicloud/advisor-chart \
  -n advisor --reset-then-reuse-values \
  --set catalog.caBundle.existingConfigMap=corp-ca
```

The chart mounts that ConfigMap read-only at `/etc/ssl/advisor-ca` and points `SSL_CERT_FILE`
at the file inside it.

**The bundle must be complete.** `SSL_CERT_FILE` *replaces* the default trust store — it does
not extend it. A ConfigMap containing only your corporate root will make the catalog reachable
and break every other TLS call the pod makes, including the cloud APIs behind Tier 3 and Tier 4.
Concatenate onto a full bundle, as above.

A ConfigMap rather than a Secret is deliberate: a CA certificate is public by design — it
is precisely what every client needs in order to verify the proxy.

## Step 6 — Point it at your metrics store

Right-sizing is only as good as its usage data. By default the Advisor scans Services for a known
PromQL-compatible store and uses the best one it finds:

| Recognised by name or `app` label | Default port | Query path |
|---|---|---|
| `thanos-query`, `thanos-querier` | 9090 | `/api/v1/query` |
| `mimir-gateway`, `mimir-query-frontend`, `mimir-nginx`, `cortex-query-frontend` | 8080 | `/prometheus/api/v1/query` |
| `vmselect` | 8481 | `/select/0/prometheus/api/v1/query` |
| `vmsingle`, `victoria-metrics` | 8428 | `/api/v1/query` |
| `openobserve` | 5080 | `/api/{org}/prometheus/api/v1/query` |
| `prometheus` (excluding operator, exporter, alertmanager, pushgateway, adapter, kube-state-metrics) | 9090 | `/api/v1/query` |

Longer-retention stores are preferred over a plain Prometheus, because a 7-day window needs the
history. Matching is substring-based over the Service name and its `app` labels, so a store behind
a name you chose yourself will not be found. Pin it explicitly:

```bash
helm upgrade audit oci://registry-1.docker.io/multicloud/advisor-chart --version 0.5.0 \
  -n advisor --reset-then-reuse-values \
  --set metrics.endpoint=http://prometheus-server.monitoring.svc:9090 \
  --set metrics.queryPath=/api/v1/query
```

If the store needs credentials, put them in a Secret with keys `METRICS_TOKEN` (sent as a Bearer
token) or `METRICS_USERNAME` + `METRICS_PASSWORD` (sent as Basic auth), and set
`metrics.existingSecret` to its name.

| Value | Default | Notes |
|---|---|---|
| `metrics.autodiscover` | `true` | Set `false` to scan nothing and rely on `metrics.endpoint` |
| `metrics.window` | `7d` | Look-back for steady and peak |
| `metrics.step` | `5m` | Sub-query resolution |
| `metrics.percentile` | `0.95` | The steady-state quantile |
| `metrics.org` | `default` | Substituted into the query path for OpenObserve-style tenancy |

**Honest limit:** `metrics.org` is substituted into the *path* only. A store that identifies
tenants with a request header instead (Mimir's `X-Scope-OrgID`, for example) is not supported
today — the query will reach the store and come back empty, which the console reports as "found
but no container CPU samples".

---

## Step 7 — Drive the levers

The report's headline is the cheapest fleet that packs your workloads under the levers you have
enabled. Toggling a lever recomputes in memory from a cached candidate set — no catalog calls, no
cluster access.

| Lever | On | Off |
|---|---|---|
| **Right-size** | Trim each workload toward observed usage before packing | Pack declared requests |
| **Clouds** | Any cloud, optionally narrowed by multi-select | Stay on your cloud |
| **Regions** | Any region, optionally narrowed by multi-select | Stay in your region |
| **Spot** | Spot and preemptible SKUs eligible | On-demand only |

Presets: **Conservative** (right-size, stay in your own cloud and region, on-demand — the zero-migration
floor) · **In-cloud low-risk** (right-size plus a cheaper SKU or region inside your own cloud, no
spot) · **Cross-cloud, no spot** · **Maximal** (the default — everything on).

Three properties that make the number defensible:

- **Best-under-constraints, never additive.** Turning a lever off can only lower the saving,
  because staying where you are is always in scope.
- **Bin-packed on both axes.** Benchmark CPU units *and* memory. Nothing is inflated by counting
  CPU work while ignoring the RAM that leaves that capacity unusable.
- **Withheld rather than fabricated.** GPU pods are packed and priced strictly against the same
  accelerator model. If a model has no same-model SKU in scope, the headline is withheld instead
  of guessing — there is no cross-accelerator performance normalization, so do not read the report
  as comparing one GPU model against another.

The per-workload list carries an include/exclude toggle per row. Excluding a workload drops both
its packed demand *and* its share of your current bill, so the saving stays "of the workloads in
scope" rather than a partial fleet measured against the full bill.

Every selection is also expressible as a query string, which is how you script or share a
particular view:

```
/report?right_size=0&allow_clouds=0&spot=0&clouds=aws,gce&regions=us-east-1,eu-west-1&excluded=ns/name
```

**The discount control is different from the levers, and worth a warning.**
`POST /discounts?mode=stated&effective_discount=0.22` changes state for *everyone* looking at that
Advisor and blocks on a full re-audit. `mode=default` clears it back to whatever the chart
deployed. Prefer setting `discount.*` in Helm; use the endpoint only when you know you are the
only person reading the report.

---

## Step 8 — Export the report

| You want | Get it from |
|---|---|
| The shareable page | `GET /report` |
| The same view as data | `GET /report.json` |
| The same view as a PDF | `GET /report.pdf` |

All three accept the lever and scope query parameters above, and the report's own JSON and PDF
buttons keep them in sync with what you are currently looking at — so what you export is what you
are reading, not the default view.

The first `/report` after a restart paints a loading shell that polls `GET /build.json` and
reloads itself when the audit completes. `POST /refresh` forces a rebuild.

**PDF caveat.** Each `/report.pdf` request starts a separate headless Chromium process inside the pod, with
no caching. It is fine for a handful of exports and wrong for a loop. If `pdf.enabled=false`, the
route returns 503 rather than pretending.

---

## Step 9 — Uninstall and revoke

```bash
helm uninstall audit -n advisor
```

That removes the Deployment, Service, ServiceAccount, ClusterRole, ClusterRoleBinding, the
namespaced Role and RoleBinding, the introspection DaemonSet if you kept it, any Ingress, and any Secret the
chart itself created.

**It does not remove or revoke these** — they are yours, and deliberately outlive the release:

| Left behind | Clean up with |
|---|---|
| Secrets you created by hand (`advisor-catalog`, `advisor-quota-*`) | `kubectl -n advisor delete secret <name>` |
| The `audit-advisor-quota-selection` ConfigMap (written by the pod at runtime, not owned by the release) | `kubectl -n advisor delete configmap audit-advisor-quota-selection` |
| The namespace | `kubectl delete namespace advisor` |
| Node labels you added by hand | `kubectl label node <node> <key>-` |
| Cloud IAM roles, service accounts and keys you created for Tier 4 | Delete them in the cloud. Uninstalling changes nothing there |
| Your catalog key | Ask your Multicloud contact to revoke it. Revocation takes effect on the next request |

Uninstalling does **not** revoke the catalog key, on purpose — so a reinstall does not need a new
one. If you want it dead, say so explicitly.

---

## Limits worth knowing

Plainly, because finding these out mid-report is worse than reading them now.

| What you see | What is actually true |
|---|---|
| Numbers change between two page loads | The Advisor runs a single replica and holds the report, the introspection map and the list of submitted quota requests **in memory only**. A restart loses all of it; only the quota-selection ConfigMap survives. A node reporting for the first time also invalidates the cached report on purpose, so it rebuilds with better identity |
| An empty or non-computable report | Treated as a diagnosis, never as an answer. The usual causes are no fully identified node, an unauthenticated catalog key, or GPU pods whose accelerator model has no in-scope SKU. Check the console first, not the report |
| Coverage is blank right after install | Node introspection reports on a 5-minute interval by default, and restarts the clock after every Advisor restart |
| Tier 2 shows "not enabled" although you enabled it | The tier badge reflects whether nodes have actually reported, not whether the flag is set. The two are told apart under `introspection` in `/status.json`: `silent: true` means enabled and nothing arrived, which usually means the DaemonSet pods are failing PodSecurity admission. `unidentified_nodes[].label_commands` lists the fix per node |
| A quota region shows nothing to do | Throttled regions produce `unknown` limits, and an unknown limit is never judged and produces no recommendation. Read the source note on the region before concluding it is fine |
| A clean quota bill | AWS opt-in regions are detected. Azure restricted regions and Google Cloud region enablement have no programmatic detector today, so "no findings" cannot mean "nothing is disabled" |
| The console is slow | `GET /` forces a full re-collect on every load — the cluster, the catalog, metrics, and each configured quota cloud — deliberately, because a human pressing reload expects fresh. Poll `GET /status.json` instead: it reads a 30-second-TTL cache and reports its own `age_seconds` |
| Catalog queries look throttled | Outbound catalog concurrency is capped, with retry on rate limits. Do not run parallel exports against a build that is still running |

---

## Reference

**Endpoints** (all unauthenticated — see Step 3):

| Route | Purpose |
|---|---|
| `GET /` · `GET /status.json` | Setup and status console, and the same assessment as JSON |
| `GET /report` · `/report.json` · `/report.pdf` | The savings report, in three forms |
| `POST /repack` | Recompute for a lever selection, in memory |
| `GET /build.json` · `POST /refresh` | Audit build state; force a rebuild |
| `POST /discounts` | Set or clear the stated discount (globally stateful) |
| `GET /quota` · `/quota.json` · `GET /quota/build.json` · `POST /quota/refresh` | Quota audit |
| `POST /quota/selection` | Persist your quota selection to the ConfigMap |
| `POST /quota/requests/submit` · `GET /quota/requests` | Quota submission and outcome polling — **404** unless write credentials are configured |
| `POST /quota/requests/preview` | Dry-run drafts of the same requests, plus the exact API call each would make. Read-only, makes no cloud call, and is **not** gated on write credentials — it reads the already-cached quota audit and 503s if there is none yet |
| `GET /healthz` · `GET /readyz` | Liveness and readiness |
| `POST /introspect` | Ingest from the introspection DaemonSet. In-cluster only |

**Helm value to container environment**, for anyone auditing what the pod actually receives:

| Value | Environment variable |
|---|---|
| `catalog.baseURL` | `CATALOG_BASE_URL` |
| `catalog.existingSecret` / `catalog.apiKey` | `CATALOG_API_KEY` (from a Secret, never inline in the pod spec) |
| `discount.mode` / `discount.effectiveDiscount` | `DISCOUNT_MODE` / `EFFECTIVE_DISCOUNT` |
| `regionAllowlist` / `cloudAllowlist` | `REGION_ALLOWLIST` / `CLOUD_ALLOWLIST` |
| `metrics.*` | `METRICS_AUTODISCOVER`, `METRICS_ENDPOINT`, `METRICS_QUERY_PATH`, `METRICS_ORG`, `METRICS_WINDOW`, `METRICS_STEP`, `METRICS_PERCENTILE`, and `METRICS_TOKEN` / `METRICS_USERNAME` / `METRICS_PASSWORD` from a Secret |
| `pdf.enabled` / `pdf.chromiumPath` | `CHROMIUM_PATH` (unset when disabled) |
| `quota.<cloud>.existingSecret` | `QUOTA_AWS_*`, `QUOTA_AZURE_*`, `QUOTA_GCE_SA_KEY_JSON` |
| `quota.<cloud>.workloadIdentity` | `QUOTA_AWS_WORKLOAD_IDENTITY`, `QUOTA_AZURE_WORKLOAD_IDENTITY`, `QUOTA_GCE_WORKLOAD_IDENTITY` — rendered **instead of** that cloud's Secret references, never alongside them |
| `quota.azure.subscriptionId` / `quota.gce.projectId` | `QUOTA_AZURE_SUBSCRIPTION_ID` / `QUOTA_GCE_PROJECT_ID` — identifiers, not credentials, so they render as plain values |
| `quotaRequests.<cloud>.existingSecret` | `QUOTA_REQUESTS_AWS_*`, `QUOTA_REQUESTS_AZURE_*`, `QUOTA_REQUESTS_GCE_SA_KEY_JSON` |

Cloud credentials are deliberately prefixed so they can never be picked up as ambient credentials
by a cloud SDK, and read credentials never share a Secret or a variable with write credentials.

## What changed in 0.5.0

Read this before upgrading an existing release. It is a minor bump rather than a patch because
one change is **breaking**: a values file that installed cleanly at 0.4.0 can now be refused.

**0.4.0 is the previous published chart**, so `0.4.0 → 0.5.0` is the real step for anyone on the
published stream.

**Breaking — an unknown value is now rejected instead of ignored.** The chart ships a
`values.schema.json`, and Helm checks your values against it before rendering anything. Every
earlier release accepted a misspelled or invented key in silence: the install reported success and
the setting you thought you had changed did nothing at all. That is the defect described in
[Step 2](#step-2--install-the-chart), and closing it is what makes this bump breaking — the same
values file that installed cleanly at 0.4.0 now fails if it carries a key the chart does not
define. A typo you have been carrying for months surfaces here, as a refusal rather than as a
setting that never applied.

Check before you upgrade, without touching the cluster:

```bash
# what your release actually sets today
helm -n advisor get values audit

# renders locally, applies nothing — the schema refuses the same keys it would refuse on upgrade
helm template audit oci://registry-1.docker.io/multicloud/advisor-chart \
  --version <version> -f your-values.yaml
```

A rejection names the path it refused, so the fix is usually to delete one line. Note that the
schema catches an unknown key and a wrong type; it cannot catch a key the chart defines but no
template reads, which is a different defect and is checked by other means.

**New in 0.5.0 — Tier 3 actual negotiated pricing.** The Advisor can price your current bill at
the rates you actually pay rather than public list, from your own cloud's billing data. The chart
surface is real and reaches the pod.

**The three clouds are not at the same maturity, and the difference is recorded per cell rather
than described in general terms.**

| Cloud | Cell | What that means |
|---|---|---|
| AWS | `validated` (2026-08-03) | A live billing read ran and its rates were cross-checked against `aws ce get-cost-and-usage` to six decimal places |
| Google Cloud · Azure | `drafted` | Built and wired, but no live read against a real billing account has been recorded. Treat any figure as indicative, and do not request the billing role for a production account on the strength of this release |

Worth knowing why AWS's cell moved when it did: the *first* live call failed outright — a
malformed Cost Explorer filter returned `400 ValidationException` and the whole read was dead —
while every mocked test was passing. The marker moved after that was fixed and the re-run was
cross-checked, which is the bar the marker is meant to carry.

On all three clouds the **grant** is a separate question from the client. The commands this
release hands your approver have not themselves been run as written; the AWS validation
ran through a broad founder identity. See [Tier 3](#tier-3--actual-negotiated-pricing).

**Tier 2 now tells you when it was blocked rather than reading as "off".** A node-introspection
DaemonSet refused by a namespace's PodSecurity admission and one that was never installed used to
look identical in the console — both simply "not active". They are now separate facts: what the
chart asked for, what actually reported in, and the cause when the two disagree. If the cause
cannot be read — the published chart's ClusterRole deliberately withholds `get` on `namespaces` —
the symptom and its remediation are still shown, and only the cause degrades.

**Behind a TLS-intercepting egress proxy, the catalog client can now be given your CA.** Set
`catalog.caBundle.existingConfigMap` to a ConfigMap holding a **full** bundle. See
[Egress proxies](#egress-proxies-and-tls-interception) — and read it first, because
`SSL_CERT_FILE` replaces the trust store rather than adding to it.

**Unchanged.** The Kubernetes permission set is the same as 0.4.0 — the upgrade asks your cluster
for nothing new. The one RBAC-adjacent addition is optional: if you set
`serviceAccount.annotations`, they land on the ServiceAccount so a cloud can bind a read-only role
to it for Tier 3 and Tier 4. Nothing renders unless you set them, and nothing static is stored.

## What changed in 0.4.0

Read this before upgrading an existing release. It is a minor bump rather than a patch because
one change is **breaking**: an upgrade that changes nothing in your values file can now fail.

**0.3.8 is the previous published chart.** `0.3.9` exists as a container image but was never
pushed as a chart, so `0.3.8 → 0.4.0` is the real step for anyone on the published stream. If you
saw `0.3.9` in a console snippet or a doc and got a `not found`, that is why.

**Breaking — the Advisor now refuses to render while it is both MCP-enabled and published.**
The 0.4.0 chart adds an in-cluster MCP server, on by default, mounted at `/mcp/` on the same port
as the console. No Advisor route has authentication, so port-forward — and therefore your
Kubernetes RBAC — is the gate. Publishing the Service removes that gate for **every** route at
once, `/mcp/` included, so the chart treats the combination as a render-time failure instead of
quietly making an unauthenticated endpoint reachable from outside the cluster.

You are affected if your current release sets either of these:

| Setting | What to do |
|---|---|
| `ingress.enabled=true` | Add `mcp.enabled=false` to keep the Ingress, or drop the Ingress and reach the console with `kubectl port-forward` |
| `service.type` anything but `ClusterIP` or `ExternalName` | Same choice: `mcp.enabled=false`, or `service.type=ClusterIP` |

`service.type` is an **allowlist** while MCP is enabled — exactly `ClusterIP` and `ExternalName`,
with anything else refused, including a value that differs only in case or carries whitespace from
an interpolated CI variable. Use `--set mcp.enabled=false`, never `--set-string`: a quoted
`"false"` reads as *enabled* to the pod, so the chart rejects it rather than accepting a value that
would invert your intent.

Check before you upgrade, without touching the cluster:

```bash
# what your release actually sets today
helm -n advisor get values audit

# renders locally, applies nothing — same failure, same message
helm template audit oci://registry-1.docker.io/multicloud/advisor-chart \
  --version <version> -f your-values.yaml
```

**Not breaking, but decide it deliberately.** The MCP server is how an AI agent drives the
Advisor — read, plan and act tools plus versioned `guidance://` resources, all served from the
pod. See the [MCP reference](mcp-reference.md). Because it is on by default, an upgrade turns it
on for you. Nothing reaches it until something connects, but when something does, the read tools
return real identifiers — namespaces, workload names, node names — and those go wherever that
agent runs, which may be a hosted model. That is a new way for your data to leave the cluster at 0.4.0, separate from
what the Advisor *sends* on its own. Read
[what leaves your cluster](what-the-agent-does.md#what-leaves-your-cluster), then either accept it
or set `mcp.enabled=false`, which leaves 0.4.0 behaving like 0.3.x.

**Unchanged.** The chart's RBAC is the same permission set as 0.3.x — the upgrade asks Kubernetes
for nothing new — and the Advisor's own outbound queries to the catalog are still abstract:
a benchmark floor, a memory floor, a GPU class, a region set.

---

## Related

- [Getting started](getting-started.md) — the same journey with an agent driving it
- [What the agent does](what-the-agent-does.md) — scope, credentials, revocation
- [Permissions reference](permissions.md) — every permission, with a reason for each
- [Quota](quota.md) — what gets requested, realistic timelines, and the honest gaps
- [Troubleshooting](troubleshooting.md) — organised by what you see
