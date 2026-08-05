# Multicloud skills

```bash
claude plugin marketplace add multicloud/skills && claude plugin install multicloud-advisor@multicloud
```

Then tell your agent: *"audit my cluster with the Multicloud Advisor."*

Not using Claude Code? Any agent that speaks MCP can follow the same instructions — point it at
<https://multicloud.io/agent/skill.md> and tell it to read that URL and follow it. You lose
automatic triggering (you have to ask for it by name) and gain a copy that is never stale, because the fetch
happens per session.

## What you get

The Advisor answers one question about your Kubernetes cluster: **what would the same work cost
somewhere else?**

It prices the performance-normalized compute you run today against every major cloud's spot and
on-demand markets, packs your actual workloads onto the cheapest fleet that fits, and shows you
the difference. Every figure is bin-packed on both CPU and memory (each workload is fitted against both limits at once), so a saving is never inflated
by counting CPU work while ignoring the memory that leaves capacity unusable.

Your own agent drives all of it: installs the Advisor, works out what access would improve
accuracy, prepares two scoped access requests per cloud account for you to approve, explains the
report, and files quota increases using **your** credentials from **your** machine.

Two properties hold throughout, and both are things you can check rather than things we promise:

- **On the agent path, the Advisor never writes to a cloud.** The MCP surface has no tool that
  submits to a cloud and no tool that accepts a credential — when something must be created in a
  cloud, your own credentials do it, from your own machine, under your own identity. That claim is
  scoped, because the chart does ship one opt-in, **default-disabled** console-only
  quota-submission path (`quotaRequests.*`); on shipped defaults it is unconfigured, its routes
  return 404, and nothing in the agent flow enables it.
- **Nothing about your workloads reaches Multicloud.** What reaches our catalog is abstract
  resource-class queries plus the instance types and regions of the nodes you already run. Your
  **agent** is a different destination and a deliberate one — it is served your namespace and
  workload names so it can explain your bill, and what it reads goes wherever that agent runs.

[docs/what-the-agent-does.md](docs/what-the-agent-does.md) shows you how to verify each of these
yourself, including the one that watching the pod's egress cannot tell you.

## The shelf

| Skill | Status | Does |
|---|---|---|
| `multicloud-advisor` | Available | Installs the Advisor and connects your agent to it |
| `skipper-onboard` | Name reserved | Onboarding onto Skipper |
| `skipper-deploy` | Name reserved | Deploying with Skipper |

Reserved names are listed here rather than as entries in
[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json): a manifest entry whose
`source` directory does not exist is a broken marketplace, not a reservation.

## Documentation

Synced from the authoring home in the Multicloud platform repo — edit it there, not here. See
[scripts/sync-docs.sh](scripts/sync-docs.sh).

| Document | Reader |
|---|---|
| [getting-started.md](docs/getting-started.md) | You, first |
| [what-the-agent-does.md](docs/what-the-agent-does.md) | Your security reviewer |
| [permissions.md](docs/permissions.md) | Whoever grants cloud access |
| [manual-install.md](docs/manual-install.md) | Anyone who wants no agent involved at all |
| [quota.md](docs/quota.md) | What gets requested, and the realistic timelines |
| [troubleshooting.md](docs/troubleshooting.md) | Organised by what you see, not by cause |
| [mcp-reference.md](docs/mcp-reference.md) | Driving the Advisor from any MCP client |

**The Advisor works with no agent at all.** [manual-install.md](docs/manual-install.md) is the
complete path by hand, and it is kept working on purpose — it is the proof that the agent is a
convenience rather than a dependency.

## Releasing

**Bump `version` in the plugin's `plugin.json`, or the change reaches nobody who already has it.**
`claude plugin update` compares versions, not content: an unchanged version reports *"already at
the latest version"* and installs nothing. Pushing a fix without a bump looks like a successful
release from every angle except the only one that matters. It happened three times in one day
before anyone noticed, so it is checked rather than remembered:

```bash
scripts/check-release.sh      # fails if a plugin changed since its last tag without a bump
claude plugin tag plugins/<name>
git push --tags
```

**Which component moves: fixes are patch bumps** — `0.2.0` → `0.2.1` → `0.2.2`. A minor bump is
for genuinely new capability, not for correcting behaviour that was already there. The version is
customer-visible and is the only signal anyone gets about what a release contains; inflating it
for fixes makes it meaningless to someone deciding whether an update is worth a session restart.
`check-release.sh` catches a missing bump but cannot tell you which component you should have
moved — that judgement is this rule.

Updates are pull-based and manual at the customer's end too. Someone who added this marketplace
earlier keeps serving themselves an older copy until they run `claude plugin marketplace update
multicloud`, and `claude plugin update` needs a session restart to take effect. Neither is
something a push can force, which is worth remembering before concluding that a fix is live.

## The audit trail

[`audit.py`](plugins/multicloud-advisor/skills/multicloud-advisor/scripts/audit.py) writes the
per-run log your agent keeps: every command, its exit code, its output. **It lives on your machine
and never comes back to us.** We have no mechanism to read it and do not want one. Run it with
`--help`.

The agent redacts secrets before writing (it replaces secret values with placeholders), and the script carries a second, independent check (a backstop) that catches common
shapes — PEM blocks, AWS key ids, secret-ish `key=value` pairs. Treat the backstop as a safety
net rather than a guarantee: a credential in a shape it does not recognise reaches the file, so
the log is sensitive and is created `0600` accordingly. You can check the net yourself:

```bash
python3 plugins/multicloud-advisor/skills/multicloud-advisor/scripts/verify_audit_redaction.py
```

## License

Proprietary — see [LICENSE](LICENSE). This repository is **public so you can read it before you
run it**, not open source. You are licensed to run these Materials against infrastructure you
own or administer; redistribution and derivative works are not permitted. Anything the Materials
produce on your machine, including the audit log, is yours.
