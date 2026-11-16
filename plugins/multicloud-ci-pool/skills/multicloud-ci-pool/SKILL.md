---
name: multicloud-ci-pool
description: Use when someone wants Multicloud CI runners - GitHub Actions self-hosted runners on machines in their own AWS account - for example to create a CI pool for a GitHub organization, pick runner sizes or runs-on labels (multicloud, multicloud-large, -no-spot), connect the GitHub App, run a first workflow job, or pause or delete a CI pool.
---

# Multicloud CI runners for GitHub Actions

A CI pool runs GitHub Actions jobs on machines in the user's own AWS account. A workflow picks
it with one label: `runs-on: multicloud`. The commands are in `flows/ci-pool.json` next to this
file. `who_kind`: `agent` = run it; `ask` = show, ask, then run; `user` = the user does it; `page` =
information for the user, nothing to run.

## Before you start

You need (ask the user, or take it from the onboarding ledger):
- a **connected, verified AWS cloud account** and its cloud-account ID (`mctl cloud-account list`,
  first column). None: use skill `multicloud-connect-aws`.
- the **GitHub organization** the runners serve. The user must be an owner of it for the GitHub App
  step: ask them to open `https://github.com/organizations/<org>/settings/apps`. If GitHub shows the
  page, they are an owner. If not, a GitHub owner of the organization must open the link later.
- the **region list** and the **cost cap** for all runners together (USD per hour). Ask both; the
  flow's `us-east-1` and `$2` are examples.
- the **runner sizes**: `small`, `medium`, `large`, `xlarge`. Each has a `-no-spot` twin (never
  interrupted) and a `-spot-only` twin (waits for spot).
- **macOS, Linux or Windows** means the user's own computer. The runners are always Linux
  machines. On Windows, run the commands inside WSL (see skill `multicloud-workstation`).

**GPU runners are not available yet.** The API refuses a GPU class (422, "GPU classes are enabled
in a later release"). Say so when the user asks for GPU runners, and offer a CPU size now, or
skill `multicloud-extend` (a GPU for their own cluster).

## Rules that do not bend

1. **Never handle a GitHub token or a GitHub App key.** You never need one: Multicloud registers
   the App and keeps its key. Do not run `gh auth token`, and do not ask the user to paste a token.
2. **Ask before you create, pause or delete a pool**, and before you push a workflow to the user's
   repository. Say the cost cap in the create question.
3. **Never use `self-hosted` labels.** The labels are `multicloud`, `multicloud-<size>`,
   `multicloud-<size>-no-spot` and `multicloud-<size>-spot-only`.

## Step 1: Create the pool (stage `pool`)

1. `classes`: show the sizes.
2. `create-pool` (ask): fill in the GitHub organization, the cloud-account ID, the classes, the cap
   and the region list (`--set regions=<r1>,<r2>`; without it, every region of the account). The
   output ends with `Next: mctl pool show <id>` and a `quota NOTE` line (spot quota is not checked
   for pools on a cloud account). To check quota, run `mctl cloud-account verify <id>`: a
   `quota LOW` line there means skill `multicloud-quota`.
3. `wait-ready`: `mctl pool show ci` (status, classes, GitHub organization; it shows no GitHub App
   state).

Errors: exit 3 or 403 → the sign-in may not create pools on a cloud account (organization owner, or
an API key with the Infrastructure scope). `ACCOUNT_NOT_READY` → verify the account first.

## Step 2: Connect GitHub (stage `github-app`)

Today the customer tools (`mctl`, the MCP server, the console) have no command for this step.
The Multicloud contact starts it and sends the user a one-time link (step `contact`). A customer
with no named contact writes to support@multicloud.io with the pool name and the GitHub
organization. Tell the user
exactly what the step says, especially: **do not change the App name** on the GitHub form (an
edited name makes the App unusable). Hand back `status=blocked who=multicloud-contact
github_app=handed_over`, and continue with Step 3 when the user says the App is installed.

## Step 3: First job (stage `workflow`)

`runs-on` (ask): the test workflow from the flow, in a repository of the organization. The user
starts it from the Actions tab. If the user wants you to write the file and push it, ask first
and use their normal git; never force-push. Done when the job log shows `hello from Multicloud`.
Then show the labels from step `labels`: only the sizes in the pool's classes get a runner.

## Pause or delete (stage `pause`)

- No jobs for a while: `mctl pool hibernate ci` (ask). A hibernated pool runs no runner, so a job with its labels does not start until
  `mctl pool wake ci --wait`.
- Delete only on request (ask; cannot be undone). The user then removes the GitHub App in GitHub.

## Hand back

```text
MULTICLOUD-RESULT skill=multicloud-ci-pool status=<done|blocked|failed> pool=<name> classes=<list> github_app=<handed_over|installed> first_job=<yes|no>
```
