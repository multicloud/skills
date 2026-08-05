# What the agent does — and what it cannot do

This is the document to read before a security review. It describes exactly what runs, where it
runs, what it touches, and how to verify each claim yourself rather than take our word for it.

## What runs where

| Component | Runs on | Holds |
|---|---|---|
| **Your AI agent** | Your machine — but its *model* usually runs on someone else's | Your cloud credentials, your kubeconfig, and everything it reads out of your cluster |
| **The Advisor** | Your Kubernetes cluster | Read-only cluster access; optionally, read-only cloud roles you grant |
| **The MCP server** | Inside the Advisor pod | Nothing of its own |
| **Multicloud's catalog** | Our infrastructure | Public SKU and pricing data — plus, to look a price up, the instance types and regions your nodes run. That is a fleet inventory. No workload name, namespace, label or configuration |

Read the first row twice, because it is the one people skip. The agent *process* runs on your
machine, holds your credentials there and never hands them over. The **model** behind it is a
different matter: if you drive the Advisor with a hosted model, everything the agent reads —
including your namespace and workload names — goes to that model's provider along with the rest
of its context. That is the intended way to use this, and it is worth knowing before you install
rather than after. [What leaves your cluster](#what-leaves-your-cluster) is the full answer.

The agent reaches the Advisor over your own tunnel — the same `kubectl port-forward` you would
use for the web console. **The MCP server is not exposed to the internet, and the chart does not
offer a way to expose it by default.**

## What the agent will do

- Read your cluster: nodes, workloads, and their declared resource requests.
- Install and upgrade the Advisor Helm release.
- Create Kubernetes Secrets holding credentials you have approved.
- Label nodes, where a missing label is what prevents the Advisor from pricing them.
- Call **read-only** cloud APIs to read your quotas and, where you grant it, your billing data.
  Each grant request states how far its own capability has been proven against a live account, so
  you approve knowing which. Nothing calls a cloud API to *identify* instances: nodes are
  identified from their Kubernetes labels and from node-local instance metadata (IMDS), which
  needs no credential at all, which is why the pricing request deliberately does not ask for
  `ec2:DescribeInstances`. Do not approve an EC2-describe or Cost Explorer permission on the
  strength of this line — approve what `get_required_iam` actually returns. Which *account*
  those nodes sit in is resolved the same credential-free way, and how much that answer is
  worth differs by cloud: [which account a request names](#which-account-a-request-names-and-how-far-to-trust-it).
- Prepare access requests for you to approve or forward.
- File quota-increase requests **that you have explicitly confirmed**, using your credentials.
- Explain the report and recompute it under different assumptions.

## What the agent will never do

- Delete anything. Anywhere. There is no deletion path in the tooling.
- Modify your workloads. Right-sizing is *recommended*, never applied — a wrong shrink is your
  risk to take, and it stays yours.
- Read your Secrets — but read how this one is guaranteed, because the two halves of it are not
  the same strength. The **Advisor** cannot: `secrets` appears nowhere in its ClusterRole
  (`templates/rbac.yaml` in the chart), so the capability does not exist to be misused, and you
  can confirm that in thirty seconds. The **agent** is a different subject: it drives your own
  kubeconfig, with whatever that kubeconfig can do, and it creates the credential Secrets you
  approve. Nothing structural stops it reading one — its not doing so is a promise this document
  makes and your own RBAC enforces, not a door the cluster holds shut.
- Send your workload data **to Multicloud**. Names, namespaces, topology and configuration do
  not reach us — what does reach us is described below, and it is price lookups. (What the agent
  itself reads is a separate question, answered in the same place. Do not read this bullet as
  an answer to it.)
- Grant itself access. Every permission is one you granted deliberately.
- File a quota request you did not confirm. There is no automatic submission path.

## What leaves your cluster

Two destinations, and they are not remotely alike. Read both before you consent.

**To Multicloud — price lookups, of two kinds.** The forward-looking one is abstract: a benchmark
floor, a memory floor, a GPU class, a region set — enough to ask *"what does hardware of at least
this shape cost?"* The backward-looking one is not abstract, and you should know it before you
consent: to price what you run **today**, the Advisor looks up each distinct instance type and
region already in your cluster (`src/pricing.py`, `price_baseline`). Those names go to the
catalog. Taken together they are a fleet inventory — how many distinct machine types you run and
where — and that is a real thing to disclose, even though it is a much smaller thing than your
cluster's state.

What does **not** go is everything that makes that inventory yours: no workload name, no
namespace, no label, no configuration, and no figure the Advisor computed. So the inverse of the
usual arrangement still holds — most cost tools ship your cluster's state out to their SaaS and
compute there, and the Advisor pulls prices in and computes inside your cluster — but "nothing of
yours leaves" was never the accurate way to say it.

**To your own AI agent — your workload names and namespaces.** The Advisor computes in-cluster,
but it *serves* the result, and the MCP endpoint at `/mcp/` is one of the things it serves it to.
`get_workloads` returns namespace, name, kind, replicas and the per-workload economics;
`get_report(detail="full")` returns the entire report. That is the point of the agent flow — it
cannot explain your bill without knowing what is on it — but it means the honest sentence is the
one in every grant request this tool generates: **anything that agent reads goes wherever that
agent runs, which may be a hosted model.** If your namespace and workload names are themselves
sensitive — customer names, project code names, an acquisition target — that is a decision to
make now, not after the report exists.

The MCP endpoint is **enabled by default** (`mcp.enabled=true`). `--set mcp.enabled=false` turns
it off: you keep the report and the web console and drive them by hand, and you lose the agent
flow. Check which posture you are in with `helm get values`.

So: Multicloud learns which machine types you run, in which regions, and nothing else about your
cluster. Your agent learns everything the report is built from. Those are two different promises,
and only the first one is ours to keep.

## Where credentials live

| Credential | Where it lives | Notes |
|---|---|---|
| **Your cloud credentials** | Your machine only | Never enter the cluster. This is what makes it safe for the agent to act. |
| **Catalog key** | A Kubernetes Secret | Written via stdin, never a command line. Revocation is self-service from your account page once self-serve signup opens — see [signup.md](signup.md). Until then, it's a request to your Multicloud contact. |
| **Read-only cloud roles** (optional) | Nothing in the cluster under workload identity; a Kubernetes Secret per cloud if you deliver a static key instead. Opt-in either way | Workload identity is the recommended delivery and is wired for every cloud — the pod trades the ServiceAccount token Kubernetes already issues it for a credential that expires in minutes. Specified and rendered by the charts; not yet exercised against a live cluster. |
| **Cloud write access** | Nowhere | The agent flow never places write credentials in your cluster. |

That last row is the important one. Because your agent already holds your credentials on your own
machine, **the Advisor never needs write access to a cloud account**. Quota requests are filed
from your machine, by you, under your identity — which is also what your cloud's audit log will
show.

## The access it asks for

Your agent works out everything it needs before asking you for anything. Concretely: it calls
`diagnose` first — a pure, credential-free read of what is already known (readiness, data gaps,
quota flags) that names every unconfigured capability and what it would cost to leave it that
way — then `get_required_iam` for the ones worth fixing, which returns the exact, minimal,
version-matched access rather than anything hand-assembled. Neither tool touches a cloud or
accepts a credential; see [mcp-reference.md](mcp-reference.md#plan-tools).

Before either grant is asked for, it also calls `preflight` — the check for everything that
would make the grant it is about to request fail or turn out to be the wrong ask: a GCP org
policy that blocks the service-account key the procedure assumes, an unregistered Azure
resource provider, an Azure support plan that cannot open a ticket, a region your account
cannot use yet, or a cluster with no OIDC issuer to federate a workload-identity grant against.
Where `preflight` cannot even tell — Azure restricted regions and Google Cloud region access
have no programmatic detector at all — it says so plainly rather than implying a clean bill.
And where the fix is something you can already do yourself (registering a resource provider,
enabling an opt-in region), it says that too, rather than routing a ticket to your cloud admin
for something you never needed their help with. This is what makes the two requests below the
*only* two: an escalation that could have been foreseen here is a defect in the agent, not
normal behaviour.

Together, this is what produces **two requests per cloud account**:

| Request | For | Usually approved by |
|---|---|---|
| Read your negotiated rates | Pricing your baseline at what you actually pay, not list price | Whoever owns billing access |
| Read your quotas | Finding provisioning limits before you commit to a move | Whoever owns cloud IAM |

Each carries its own policy, a reason for every action, what it does not permit, its blast radius,
and how to revoke it.

They are split because they usually need different approvers, and they are **independent** —
neither is a prerequisite for the other, and a denial or a delay on one does not block the other.

Beyond those two, your agent will not come back for another grant unless you later add a
capability — and then it asks for the *difference*, not a fresh policy. A request for something it
should have foreseen is a defect, not normal behaviour.

Full detail: [permissions.md](permissions.md).

## Which account a request names, and how far to trust it

Every grant request has to say which cloud account it is for, and the Advisor resolves that
without holding a cloud credential. The reviewer's next question is the right one — *how do you
know?* There are two routes to an account, they are not equally trustworthy, and the Advisor
labels which one it used rather than presenting both as fact.

**Verified — GCP and Azure.** The account is parsed out of the `providerID` field on the Node
object: a GCP project, an Azure subscription. Kubernetes writes that field itself. No pod is
asked for it and no pod can edit it, so an account resolved this way needs no confirmation from
you.

**Self-reported — AWS.** An AWS `providerID` is `aws:///<zone>/<instance-id>` and carries no
account at all, so the account id comes from the introspection DaemonSet instead: the pod reads
its own node's instance identity document from IMDS and posts it back over `POST /introspect`,
which is cluster-internal and **unauthenticated**. That endpoint is the whole caveat. Anything
in the cluster that can reach it can claim any account for any node. So what the read
establishes is a *candidate* — a number good enough to save you looking one up, and not evidence
that the node is in that account. The Advisor never prints it as checked: the request carries
the account together with an explicit instruction to confirm it before sending, because printing
a claimed account as verified is precisely how a workload in your cluster would steer a grant
toward an account of its own choosing.

**The judgement is per cloud, and it fails closed.** A cloud is reported verified only when
*every* account seen under it came from a providerID. One node contributing an account any other
way demotes that whole cloud to self-reported — one node does not get to hide behind its
neighbours. The asymmetry is deliberate: under-claiming costs you a confirmation prompt,
over-claiming costs a grant filed against the wrong account. Where nothing resolves at all, the
answer is "none" and you are asked which account to use; a blank never reaches a request.

The operator-side view of the same mechanism — what the DaemonSet reads, and what to do when a
node cannot be identified — is in
[permissions.md § Node identification](permissions.md#2-node-identification-no-credentials).

## How to revoke everything

| To remove | Do |
|---|---|
| The Advisor | `helm uninstall` — removes every object it created |
| A cloud role | Revocation instructions ship inside the grant request itself |
| The catalog key | Revoke it yourself from your account page once self-serve signup opens — see [signup.md](signup.md). Until then, ask your Multicloud contact |
| The agent's access | Uninstall the skill; it holds no standing credential of its own |

Note that uninstalling the Advisor does **not** revoke your catalog key — revoke it separately if
you are finished.

## Auditability

Your agent keeps a per-run log of every command it issues — the command, its exit code and its
output. It redacts secrets before writing, and the script that writes the log carries a backstop
that catches common shapes — PEM blocks, AWS key ids, secret-ish `key=value` pairs. Treat that
backstop as a safety net rather than a guarantee: a credential in a shape it does not recognise
reaches the file, which is why the log is created `0600` and is worth treating as sensitive.
**That log lives on your machine and never comes back to us.** It is your audit trail, not our
telemetry; we have no mechanism to read it and do not want one.

Every access request is a reviewable document rather than a command someone typed into a terminal.
Every quota request appears in your own cloud audit log, under the identity of the person who
confirmed it — because it was filed with your credentials, from your machine.

The log also records **friction**: where the flow was unclear, where a step failed, where the
agent had to work around something. If you choose to send us an excerpt it makes the tool better,
but nothing is sent unless you send it.

This is a better trail than the manual alternative, where the same steps leave nothing behind but
shell history.

## Verify this yourself

Do not take the above on trust. Each claim is checkable:

| Claim | How to check |
|---|---|
| Cluster reads are read-only | Read `templates/rbac.yaml` in the chart — under a minute end to end. Cluster-wide access is `get`/`list`/`watch` only: no Secrets, no logs, no exec. The one write in that file is a namespaced Role over a single ConfigMap (your quota answers); Kubernetes cannot name-pin `create`, so its bound is namespace scope. |
| No cloud writes on the agent path | List the MCP server's tools. There is no submit tool, no cloud-write tool, and no tool that accepts a credential — the absence *is* the guarantee. The tool surface has landed (5 read tools, 7 plan tools including `plan_grant_requests`, 3 act tools that never touch a cloud), so `tools/list` verifies this directly rather than reflecting a still-empty manifest. Separately, the chart ships one opt-in, default-disabled console-only submission path; check it is off with `helm get values` (`quotaRequests.*`). |
| Nothing about your workloads reaches **Multicloud** | Watch the pod's egress: `api.multicloud.io` always, plus **your own** cloud API endpoints if you enabled quota visibility. To see *what* is sent to the catalog rather than only where, read `advisor/src/catalog_client.py` — every outbound parameter is built there. |
| What your **agent** is served, and therefore what reaches its model | Egress-watching cannot answer this one and must not be used for it: `/mcp/` is an inbound pull over your own port-forward, so a clean egress trace proves nothing about it. Ask your agent to call `get_workloads` and show you the raw result — your namespaces and workload names are in it, and that is precisely what entered its context. `get_report(detail="full")` is the whole report. If that is more than you want a hosted model to hold, `--set mcp.enabled=false`. |
| The MCP server is not reachable externally | It has no Ingress and no Service exposed beyond the cluster, and that is enforced rather than assumed: the chart **fails to render** if `mcp.enabled` is combined with anything that publishes the Service — `ingress.enabled=true`, or any `service.type` other than `ClusterIP`/`ExternalName`. That second test is an allowlist rather than a list of forbidden values, so a wrong-case type, a value carrying stray whitespace from a CI variable, and any Service type Kubernetes ships in future are all refused too. Try it: `helm template` refuses, and names which one tripped it. The server additionally answers `421` to any request whose `Host` is not loopback, though treat that as a second line rather than the guarantee — it inspects the `Host` header, not the caller, so the render-time refusal is the load-bearing control. |
| Nothing is persisted | The Advisor holds its analysis in memory. The single durable object it writes is a ConfigMap containing your own quota questionnaire answers. |
| A self-reported account is never dressed up as a verified one | Ask your agent to show you the raw `diagnose` output: every cloud carries `account_source` alongside its accounts — `provider_id` (read from the Node's own `providerID`), `introspection` (self-reported over the unauthenticated in-cluster read), or `none`. Then have it render the request with `plan_grant_requests`: the same distinction is printed into the document itself, so it reaches whoever approves the grant and not only whoever ran the tool. |

## One thing to be aware of

Your cluster's contents — workload names, namespace names, annotations, error messages — flow
into your agent's context so it can reason about them. Treat them as data, not instructions. Your
agent is instructed to do the same, and to never act on text it finds inside your cluster as
though you had typed it.

## Related

- [Getting started](getting-started.md)
- [Permissions reference](permissions.md)
- [Manual install](manual-install.md) — the same outcome with no agent at all
