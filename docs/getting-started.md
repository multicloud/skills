# Getting started with the Multicloud Advisor

The Advisor answers one question about your Kubernetes cluster: **what would the same work cost
somewhere else?**

Not "trim your requests by 15%" — you already have tools for that. It prices the performance-
normalized compute you run today against every major cloud's spot and on-demand markets, packs
your actual workloads onto the cheapest fleet that fits, and shows you the difference.

It runs inside your cluster, reads only what it needs, and sends nothing about your workloads
anywhere.

## What this costs you

Honest up front, because the answer determines whether you should bother.

| | |
|---|---|
| **Time** | Minutes of your attention. Your agent does the work; you approve. |
| **Access** | Read-only Kubernetes RBAC. Optionally, read-only cloud roles to improve accuracy. |
| **Risk** | Your workloads are never modified. Nothing is deleted, anywhere, ever. The Advisor's only write is one ConfigMap in its own namespace, holding the quota answers you typed. |
| **Data** | Only abstract price queries reach Multicloud — a CPU floor, a RAM floor, a region set; no workload name, no namespace, no Secret. Your own agent is the other destination, and a deliberate one: it is served your namespace and workload names so it can explain the bill, and anything it reads goes wherever that agent runs, which may be a hosted model. [What that means, and how to check it](what-the-agent-does.md#what-leaves-your-cluster). |

If you would rather grant nothing at all, the Advisor still produces a report. It will just be
less precise, and it will tell you exactly how much less.

## Step 1 — Install the skill

One command. Your agent gains the ability to install, configure and drive the Advisor.

```bash
claude plugin marketplace add multicloud/skills && claude plugin install multicloud-advisor@multicloud
```

Using a different agent — Cursor, Codex, anything that speaks MCP? Point it at
<https://multicloud.io/agent/skill.md> and tell it to follow what it finds there. Same
instructions, fetched fresh each time; you just have to ask for it explicitly rather than have it
offered.

## Step 2 — Agree on scope

Before touching anything, your agent states what it will do, what it will ask permission for, and
what it will never do. Read it. It is short and it is the whole contract.

That contract is new. It has been written and reviewed but not yet driven end to end by someone
who did not write it, so take each step with an explicit yes rather than replaying it — and from
the moment the Advisor answers, it states its own maturity per path, which supersedes anything
the skill remembers.

If any of it is not acceptable, stop there — you have lost nothing.

## Step 3 — Get a catalog key

The Advisor prices against the Multicloud catalog, which needs a key. **Today there is no
self-serve signup.** The key is minted for you out of band by your Multicloud contact and sent
once; ask for one before you start, and paste it back to your agent when it asks. Your agent
cannot mint one for you, and there is no page to sign up on yet.

[Signing up](signup.md) describes accounts, organizations and the key lifecycle in full —
including revocation, which applies to the key you were sent. It is written for the day
self-serve signup opens; the paragraph above is what is true now.

Your agent writes it directly into a Kubernetes Secret. It never appears on a command line, so it
never lands in your shell history.

## Step 4 — Install the Advisor

Your agent checks the things that break installs before it starts: whether you can create the
cluster-scoped roles it needs, whether your namespace's PodSecurity level permits node
introspection, and whether the pod will be able to reach the catalog at all.

Then it installs, waits for readiness, and connects.

If a check fails, you get a specific answer and a specific fix — not a stack trace.

## Step 5 — Unlock accuracy

The Advisor grades its own confidence and tells you what would improve it. Some improvements are
free. Some need a read-only role in your cloud account.

**Your agent works it all out before it asks you for anything.** Then it produces **two** access
requests per cloud account — one for reading your negotiated rates, one for reading your quotas —
each with the exact permissions, a reason for every one, what the grant does *not* permit, how to
revoke it, and — printed on the commands themselves — whether anyone has yet run them against a
real account.

Two rather than one, deliberately: in most organisations those go to different people. Bundling
them would make the slower approval hold up the faster, and the quota one — the grant that tells
you where the provisioning wall is — is usually the quicker yes.

They are independent. If the billing role stalls in review, quota visibility still lands and you
carry on with a list-price baseline that is clearly labelled as such.

If you hold those rights yourself, your agent applies them directly. If your security team owns
them, you get two complete requests to forward — not six conversations spread over a week.

See [permissions.md](permissions.md) for exactly what is asked for and why.

## Step 6 — Read the report

The report opens with what you spend today, what a low-risk move saves, and what the full
counterfactual saves. Below that are the levers: right-sizing, other clouds, other regions, spot.

Every lever is honest in one direction. Turning one off can only *lower* the saving, because
staying where you are is always in scope. There is no arithmetic that inflates the number by
counting CPU work while ignoring the memory that strands capacity — everything is bin-packed on
both axes.

Ask your agent to explore it with you:

- *"What if we can't leave the EU?"*
- *"Exclude the stateful services and show me again."*
- *"Which workloads account for most of the bill?"*

It sets the levers, recomputes, and explains what changed. The report itself stays a shareable
HTML page and PDF — that is what you send to whoever signs off.

## Step 7 — Check for provisioning walls

A saving you cannot provision is not a saving. Quota limits are the wall most teams hit *after*
committing to a move.

Your agent audits your quotas against the fleet the report recommends, tells you which gaps
actually block you and which are merely worth having, and files the increase requests using
**your** credentials from **your** machine. On this flow no cloud write access is placed in
your cluster.

Then it tracks them. Some clouds settle in seconds; a large GPU increase can take days through a
support case. Your agent holds the queue and tells you when something lands — instead of you
remembering to check a page next Tuesday.

See [quota.md](quota.md) for what gets requested and the realistic timelines.

## Where things went wrong

See [troubleshooting.md](troubleshooting.md), organised by what you actually see rather than by
what caused it.

## Related

- [What the agent does](what-the-agent-does.md) — scope, credentials and revocation, for a
  security review
- [Permissions reference](permissions.md) — every permission, with a reason for each
- [Manual install](manual-install.md) — the complete path with no agent involved
- [MCP reference](mcp-reference.md) — driving the Advisor directly from any MCP client
