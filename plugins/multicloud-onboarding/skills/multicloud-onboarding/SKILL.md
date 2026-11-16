---
name: multicloud-onboarding
description: Use when a new customer wants to start with Multicloud from zero, run a Multicloud proof of concept (PoC) such as "Run the Multicloud GPU PoC", get onboarded, or continue an onboarding that stopped earlier (for example while AWS quota was pending). Covers every door - Extend (cloud nodes for your own Kubernetes cluster), CI runners for GitHub Actions, and the Advisor.
---

# Multicloud onboarding (orchestrator)

You take a new customer from nothing to a working Multicloud door. You do not hold the steps
yourself. You ask a few questions, run the focused skills below in the right order, pass each one
the IDs it needs, and keep a ledger so the work can continue on another day.

## Rules that do not bend

1. **Secrets stay with the user.** Never ask for, accept, read, print or store a password, MFA code,
   AWS key, Multicloud API key (`mca_…`), connect code, peering bundle or model API key. If the user
   pastes one, tell them to revoke it and make a new one. The user types secrets into their own
   terminal or browser. Never store a key in an environment setting that lasts (`setx`, `~/.zshrc`).
   A pasted secret stays in this chat's history: revoking it is the only fix, so say that first,
   even when the user is in a hurry. No step of this flow needs a Multicloud API key: `mctl auth
   login` signs in through the browser. The key is only for an optional MCP connection, which the
   user configures themselves.
2. **Browser.** You may guide the AWS console and multicloud.io, and drive the browser if you have
   browser tools. Stop before any page that shows a secret once (AWS "Create access key", the
   multicloud.io new API key): the user does that page alone. Never type into a password or MFA
   field. Ask before you accept terms.
3. **Ask before each change** that creates, costs or deletes something. State the cost for a pool.
4. **Live state wins.** The ledger says where you stopped; `mctl` says what is true. Never repeat a
   step that live state shows done (a second quota request, a second cloud account, a second pool).
5. **Check before you suggest.** Before you tell the user to install, restart or run anything,
   check on this computer whether it is already there and in the right state (the focused skill
   names the check). Suggest only what is missing, and say what you found first.
6. **Use the focused skill for each step.** Do not improvise commands. When a skill and your memory
   disagree, the skill wins; when a tool's live answer and a skill disagree, the live answer wins.

## The focused skills

| Skill | Use for | Hands back |
|---|---|---|
| `multicloud-workstation` | Windows WSL2, multicloud.io account, tools, Multicloud sign-in, optional AI connection | `os`, `run_prefix`, `org_id` |
| `multicloud-aws-account-setup` | A new AWS account, or no AWS CLI sign-in yet | `aws_account_id`, `aws_profile`, `aws_path` |
| `multicloud-connect-aws` | Connect the AWS account to Multicloud | `cloud_account_id`, `connection_dir`, `quota_low` |
| `multicloud-quota` | AWS quota for the first workload | `quota` (`enough`, `waiting`, `denied`), request IDs |
| `multicloud-extend` | Extend door: cluster checks, pool, peering, first workload, cleanup | `pool`, `peering_id`, `consumer_cluster_id`, `first_run` |
| `multicloud-ci-pool` | CI runners door | `pool`, `github_app`, `first_job` |
| `multicloud-advisor` | Advisor door (savings report) | (route only) |

**Find a skill.** If your agent has the skill installed, use it by name. Otherwise read its
`SKILL.md` from this repository at the release tag in the table at the end, from
`https://raw.githubusercontent.com/multicloud/skills/<tag>/plugins/<skill>/skills/<skill>/SKILL.md`,
and the files it names from the same folder (`flows/*.json`, and `assets/vllm-gpu.yaml` for
`multicloud-extend`). If the tag answers 404 (not released yet), use `main` instead of the tag and
tell the user so. Never copy its text into this conversation as your own
plan; follow it as written.

Every focused skill ends with one line:

```text
MULTICLOUD-RESULT skill=<name> status=<done|waiting|blocked|failed> key=value ...
```

`waiting` means time will fix it (quota, an AWS region turning on). `blocked` means a person must
act; the line names who (`who=owner`, `who=aws-admin`, `who=it`, `who=multicloud-contact`). Write
every result line into the ledger before you start the next skill.

## Step 1: Find or start the ledger

**Windows without WSL first.** On a Windows host shell where there is no WSL2 distro (any distro
works; see the check in `multicloud-workstation`, Step 1; `wsl.exe -l -v` printing usage text
counts as "none"),
run only the `windows` stage of `multicloud-workstation` first: the ledger lives inside
WSL, and the WSL install ends with a Windows restart. Tell the user, in this order: (1) "Restart
Windows now." (2) "After it restarts, open your WSL distro once (Ubuntu from the Start menu, or the one you chose) and set a Linux user name and password."
(3) "Then quit Claude Code and start it again with `claude --continue` in PowerShell, so the
Multicloud skills load. The skills are only loaded at the start of a session." (4) "Then say:
continue my Multicloud onboarding." Then stop.

**Restart rule for every step.** Whenever a step installs or updates a plugin, or changes skill
files, tell the user to restart Claude Code (`claude --continue`) before the next skill runs, and
say why in one line. Do not continue in the same session.

The ledger is `multicloud-onboarding-state.json` in `~/multicloud-onboarding/` (on Windows: the
home folder inside WSL, never under `/mnt/c`). Make the folder with mode 700 and the file with
mode 600. Keep mode 600 on every update: write a new version with `umask 077` and run
`chmod 600` on the file after the move (a rewrite through a temp file gets mode 644 otherwise). If the user keeps it elsewhere, ask for the path once and store it in the file itself.

- File exists: read it, tell the user in two lines what is done and what is next, then go to
  **Step 3: Check live state**.
- No file: go to **Step 2**.

Format (IDs and states only, nothing secret):

```json
{
  "version": 1,
  "answers": {"door": "extend", "cloud": "aws", "aws_account": "new", "os": "windows",
              "cluster": "kubectl-works", "workload": "gpu-llm"},
  "facts": {"org_id": "acme", "wsl_distro": "Ubuntu", "aws_profile": "poc", "aws_account_id": "123456789012",
            "region": "us-east-1", "cloud_account_id": 7,
            "connection_dir": "/home/ana/multicloud-aws", "kubeconfig": "/home/ana/.kube/config-poc",
            "kube_context": "default", "pool": "poc-gpu", "peering_id": 31},
  "results": {"multicloud-connect-aws": "MULTICLOUD-RESULT skill=multicloud-connect-aws status=done cloud_account_id=7 connection_dir=/home/ana/multicloud-aws"},
  "updated": "2026-11-15T14:02:00Z"
}
```

`facts` holds every ID and name a later step needs: copy each `key=value` of a result line into it,
and add a fact as soon as you learn it (the profile name, the kubeconfig path, a pool or peering
you created), not only at the end of a skill. A pool or peering created before a session broke
off is then known on resume.

## Step 2: Ask (one question at a time, each with an "other" answer)

Skip a question that the user's message already answers ("brand-new AWS account", "Windows
laptop", "my k3s cluster"), and write that answer to the ledger. Ask only what is left.

1. **Door.** "What do you want to do first?" Extend (cloud nodes, also GPUs, for your own Kubernetes
   cluster) · CI runners for GitHub Actions · a savings report for a cluster (Advisor) · other.
   - Advisor: hand over to `multicloud-advisor` and stop here.
   - Skipper or anything else: say it is not available in this flow yet, and stop.
2. **Cloud.** AWS · Google Cloud · Azure. This flow covers AWS. For Google Cloud or Azure, point the
   user to the customer guide (`mctl cloud-account create --cloud GCE|AZURE`) and stop.
3. **AWS account.** Brand new (only the root login) · Existing, I sign in with single sign-on ·
   Existing, I have an IAM user or access key · I do not know.
4. **Computer.** macOS · Linux · Windows.
5. Extend only: **Cluster.** My cluster works with `kubectl` now · I have a cluster but no access yet
   (the administrator must give a kubeconfig file and cluster-admin rights: continue, and stop
   before the cluster stage) · No cluster (Extend needs one: offer CI runners, else stop).
6. Extend only: **Workload.** One LLM on one GPU (the GPU PoC) · CPU work · other.
7. CI only: **GitHub organization** name, and which runner sizes. If the user asks for GPU runners,
   say first that GPU runner classes are not available yet, and ask one question: CPU runners now
   (recommended), or a cloud GPU for their own Kubernetes cluster (the Extend door).

Write the answers to the ledger.

## Step 3: Check live state

Run these read-only checks (skip a check whose tool is not installed yet). Use the `run_prefix`
from `multicloud-workstation` on Windows.

```bash
mctl auth status
mctl cloud-account list
mctl pool list
```

For Extend, if a pool exists: `mctl peering list <pool>`. For quota: run Step 2 of
`multicloud-quota` (`mctl cloud-account quota-plan <cloud_account_id> --region <region>`; it files
nothing).

**Live state wins over the ledger.** Correct the ledger where they differ, and say so in one line.
Example: the ledger says `quota=waiting`, and `quota-plan` shows the on-demand G and VT limit at 4
or more in the region: write `MULTICLOUD-RESULT skill=multicloud-quota status=done quota=enough
region=<r> requests=<id> filed_by=<as before>` and continue with the next skill.

## Step 4: Run the skills in order

Skip a skill whose result in the ledger is `done` and whose live state agrees.

| Door | Order |
|---|---|
| Extend, GPU LLM | workstation → aws-account-setup (if Q3 is new, or no working AWS CLI sign-in) → connect-aws → quota (goal: one on-demand L4 or A10G GPU) → extend (profile `gpu-llm`) |
| Extend, CPU | workstation → aws-account-setup (if needed) → connect-aws → quota (only if `quota_low`) → extend (profile `cpu-burst`) |
| CI runners | workstation (no kubectl, no helm) → aws-account-setup (if needed) → connect-aws → quota (only if `quota_low`) → ci-pool |

The account is already connected and verified (live state), but no connect-aws result is in the
ledger: skip connect-aws and aws-account-setup, and learn `quota_low` from
`mctl cloud-account verify <cloud_account_id>` (it reads the quotas and files nothing). In that
case `multicloud-workstation` needs only `mctl` for CI, and `mctl`, `kubectl`, `helm`, `jq` for
Extend; `aws` and `tofu` only for a step that uses them.

Pass each skill what it needs from earlier results: `run_prefix`, `aws_profile`, `aws_account_id`,
the region, `cloud_account_id`, `connection_dir`, the profile, the GitHub organization.

**While a skill is `waiting`:** tell the user what you wait for and how long it usually takes. Do
the next steps that do not need it. For Extend GPU while quota waits: run only the `cluster` stage
of `multicloud-extend` (it creates nothing that costs), never the pool. Then save the ledger and
tell the user how to continue: "Say: continue my Multicloud onboarding."

**When a skill is `blocked`:** say who must act and what to ask them, save the ledger, and stop.

## Step 5: End of each session

- A pool is awake and the user stops for the day: offer `mctl pool hibernate <pool>` (it stops the
  cost; `mctl pool wake <pool> --wait` resumes). Ask first.
- Path B was used (an IAM user access key): remind the user that the key must be deleted after the
  PoC (the `cleanup` stage of `multicloud-extend` lists it).
- Save the ledger. Tell the user, in at most five lines, what works, what waits, and the next step.

## Done

| Door | Done when |
|---|---|
| Extend GPU | The first query to the model answers. |
| Extend CPU | A test pod runs on the virtual node. |
| CI runners | A workflow job with `runs-on: multicloud` runs on a Multicloud runner. |

Then print `MULTICLOUD-RESULT skill=multicloud-onboarding status=done door=<door>` and update the
ledger.

## Tested versions

| Skill | Tag |
|---|---|
| `multicloud-workstation` | `multicloud-workstation--v0.1.0` |
| `multicloud-aws-account-setup` | `multicloud-aws-account-setup--v0.1.0` |
| `multicloud-connect-aws` | `multicloud-connect-aws--v0.3.0` |
| `multicloud-quota` | `multicloud-quota--v0.2.0` |
| `multicloud-extend` | `multicloud-extend--v0.1.0` |
| `multicloud-ci-pool` | `multicloud-ci-pool--v0.1.0` |
| `multicloud-advisor` | the newest `multicloud-advisor--v*` tag |
