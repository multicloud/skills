# Multicloud Advisor — documentation

<!-- MAINTAINERS: authoring home is docs/external/advisor/ in the platform repo. The published
     copy is https://github.com/multicloud/skills/tree/main/docs, synced by that repo's
     scripts/sync-docs.sh. Edit here — the published copy is overwritten.
     Kept as a comment on purpose: this file syncs into the public repo as docs/README.md, which
     GitHub renders as the folder index, so a visible note here is the first thing a customer's
     security team reads. It renders as nothing and still reaches the only audience it is for. -->


The Advisor answers one question about your Kubernetes cluster: **what would the same work cost
somewhere else?** It runs inside your cluster, reads only what it needs, and sends nothing about
your workloads anywhere.

## Start here

| If you want to | Read |
|---|---|
| Run an audit and see a number | [getting-started.md](getting-started.md) |
| Review this before approving it | [what-the-agent-does.md](what-the-agent-does.md) |
| Grant, review or revoke access | [permissions.md](permissions.md) |
| Do it all by hand, with no agent | [manual-install.md](manual-install.md) |
| Understand quota gaps and requests | [quota.md](quota.md) |
| Fix something that went wrong | [troubleshooting.md](troubleshooting.md) |
| Drive the Advisor from any MCP client | [mcp-reference.md](mcp-reference.md) |

## The short version

The Advisor prices the performance-normalized compute you run today against every major cloud's
spot and on-demand markets, packs your actual workloads onto the cheapest fleet that fits, and
shows you the difference. Every figure is bin-packed on both CPU and memory, so a saving is never
inflated by counting CPU work while ignoring the memory that strands capacity.

Your own AI agent can drive the whole thing: install it, work out what access would improve
accuracy, prepare two scoped access requests per cloud account for you to approve (one for pricing, one for quota), apply the result,
explain the report, and file quota increases using **your** credentials from **your** machine.

Two properties hold throughout, and both are verifiable rather than promised:

- **The Advisor never writes to a cloud on the agent path.** The MCP surface has no tool that
  submits and no tool that accepts a credential. The chart does ship one opt-in,
  **default-disabled** console-only quota-submission path (`quotaRequests.*`); on shipped defaults
  it is unconfigured and its routes return 404. See [permissions.md](permissions.md) §6.
- **Nothing about your workloads reaches Multicloud.** What reaches the Multicloud catalog is
  abstract resource-class queries — a CPU floor, a memory floor, a GPU class, a region set. To price what
  you run today, the instance type and region names of the nodes you already run also reach the
  catalog.
  No workload name, namespace, label or configuration. Your
  **agent** is a different destination and a deliberate one: the MCP endpoint (on by default)
  serves it your namespace and workload names so it can explain your bill. Anything that
  agent reads goes wherever that agent runs, which may be a hosted model.

[what-the-agent-does.md](what-the-agent-does.md) shows you how to check each of these for
yourself — including the one that watching the pod's egress cannot tell you.

## If you are reviewing this for a security team

Read [what-the-agent-does.md](what-the-agent-does.md) first, then
[permissions.md](permissions.md). Between them they cover what runs where, what each permission
grants and does not grant, its blast radius (how far the damage could reach if it were misused), where every credential lives, and how to revoke
each one.

The two facts that usually matter most in that review: your cloud credentials never reach
Multicloud (the agent's stay on your machine; any you grant the Advisor stay in a Kubernetes
Secret in your own cluster). The other: the Advisor's Kubernetes role is `get`/`list`/`watch` only — no
Secrets, no logs, no exec — in a file short enough to audit in under a minute. The one write in
that file is a namespaced Role over a single ConfigMap holding your own quota answers: `get`,
`update` and `patch` are pinned to that ConfigMap by name, and `create` is bounded by the
namespace because Kubernetes cannot pin `create` by name.
