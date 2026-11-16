---
name: multicloud-connect-aws
description: Use when someone wants to connect an AWS account to Multicloud, give Multicloud access to their AWS account, onboard AWS onto Multicloud, check whether a connected AWS account is ready, or fix "missing permissions" on a Multicloud cloud account. Drives the mctl CLI and OpenTofu/Terraform on the user's machine.
---

# Connect an AWS account to Multicloud

Multicloud runs machines in the customer's own AWS account. To allow that, the customer creates
one IAM role with a public Terraform module, and Multicloud checks the role. You do this for the
user with the `mctl` CLI and their own AWS login. The result is one line: **Ready**, or the exact
missing permissions.

## Rules that do not bend

1. **Never handle the API key.** Do not ask for it, do not accept it in chat, do not put it in a
   command, a file or an environment variable. If the user pastes one, tell them to revoke it on
   multicloud.io (Account → API keys) and make a new one. The user signs in or stores a key
   themselves, in their own terminal (step 2).
2. **Never handle the connect code.** Do not run `mctl cloud-account token` (it prints the code;
   that command is for people who apply by hand). `mctl cloud-account apply` gets the code and
   gives it to Terraform without showing it. Never read `~/.config/multicloud/credentials`, never
   print environment variables (`env`, `printenv`, `set`), and never run `tofu`/`terraform`
   `output`, `show` or `state` in the connection folder: `mctl` runs Terraform for you.
   The same holds for AWS secrets: never ask for, read, print or export AWS credential material.
   For example: never read `~/.aws/credentials` or `~/.aws/sso/cache`, and never run
   `aws configure export-credentials`, `aws configure get aws_secret_access_key` (or
   `aws_session_token`) or `aws sts get-session-token`. The user types AWS keys into
   `aws configure` themselves.
3. **Ask before every apply.** Show what the plan creates, ask one yes/no question, and run
   `apply --yes` only after a clear yes. A yes covers one apply.
4. **One connection per AWS account.** Run `mctl cloud-account list` before `create`. If the
   account is listed, use that number and its folder. Never `create --force`.
5. **Keep the folder.** The folder with `multicloud.tf` holds the Terraform state of the role.
   Never delete it, never move the state, never run `destroy` unless the user asks to disconnect.
6. **Dedicated account first (policy).** Multicloud runs GPU and CPU workloads and creates IAM roles
   in the account. Prefer a **new dedicated sub-account** for the PoC, created with Terraform or the
   steps in skill `multicloud-aws-account-setup` (Step 0). Do not connect an **existing** account
   unless the user has heard this warning and explicitly approves it:
   > Warning: this account would get a Multicloud IAM role that can start and stop compute and
   > request quota. Existing workloads and their permissions share the account. Removing the
   > connection later means `destroy` of the role. Option: a new sub-account, which keeps the PoC
   > apart from your current work.

   Ask one question: "Use a new dedicated account (recommended), or connect the existing account
   `<id>` after this warning?" Record the answer in the ledger as `aws_account_choice=new|existing`
   and `aws_existing_approved=yes` only on an explicit yes. A "yes" to another question is not an
   approval. No approval: stop with `status=blocked who=user`.

## Step 1: Check the tools

Run these and report what is missing, with the install line:

| Check | If missing |
|---|---|
| `mctl --version` | `uv tool install multicloud-cli` (or `pipx install multicloud-cli`); skill `multicloud-workstation` installs every tool |
| `tofu version` or `terraform version` (1.10 or later, which the AWS module 2.0.0 needs; `mctl` uses `tofu` when both exist) | OpenTofu: https://opentofu.org/docs/intro/install/. An older version: stop and ask the user to upgrade. |
| `aws sts get-caller-identity` | Fails, shows another account, or the user does not know their AWS profile: follow **AWS sign-in help** below. If they use a profile, use `AWS_PROFILE=<p>` in later commands. |

On Windows, run every command inside WSL (`wsl.exe -d <wsl_distro> -- bash -lc '…'`), and make the
connection folder in the WSL home folder, never under `/mnt/c` (see skill `multicloud-workstation`).

Tell the user the AWS account ID that `aws sts get-caller-identity` shows. It must equal the
account they want to connect. If it differs, stop and ask them to log in to the correct account.
The login must be able to create IAM roles and policies.

## AWS sign-in help

Many users do not know AWS CLI profiles. Explain in plain words: a **profile** is a named AWS
sign-in in `~/.aws/config`. It holds the AWS account, the role, the sign-in method and an optional
default region. `AWS_PROFILE=<name>` selects it. Then go through these steps, one at a time.

1. **No `aws` command.** The user installs the AWS CLI:
   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html (macOS:
   `brew install awscli`).
2. **Find the profile.** Run `aws configure list-profiles`. If the user names one, check only that
   one. Otherwise check each (at most 10) with
   `AWS_PAGER= aws sts get-caller-identity --profile <p> --query Account --output text </dev/null`
   (no input, so an MFA prompt fails instead of waiting), and show the user a table: profile, AWS
   account ID. A profile that fails (token, SSO, MFA or other error) is signed out.
   The user picks the profile of the account to connect. If it is signed out, the user runs
   `aws sso login --profile <p>` in their own terminal (it opens the browser) and tells you when
   done.
3. **No profile for that account.** The user makes one in their own terminal: the command asks
   questions that you cannot answer for them. Recommend single sign-on: `aws configure sso`. Tell
   them what it asks:
   - **SSO session name:** any name, for example their company name.
   - **SSO start URL:** the "AWS access portal URL", for example
     `https://my-company.awsapps.com/start`. Their AWS administrator has it. It is also in the
     IAM Identity Center console, under **Settings**.
   - **SSO region:** the region of IAM Identity Center, on the same page.
   - **Registration scopes:** keep the default.
   - The browser opens. They sign in, then select the AWS account and a role that can create IAM
     roles and policies: for example `AdministratorAccess`, or a narrower role from their AWS
     administrator.
   - **Default client region:** the first region they will give to Multicloud.
   - **Output format:** keep the default.
   - **Profile name:** a name that `aws configure list-profiles` does not show yet (an existing
     name is overwritten), for example `multicloud`.

   No single sign-on in their company (an IAM user with an access key):
   `aws configure --profile multicloud`. They type the key themselves, never in the chat.
   A brand-new AWS account (only the root login): use skill `multicloud-aws-account-setup`, then
   come back here. No AWS login at all in a company account, or no role that can create IAM roles:
   their AWS administrator must give them one. Stop until they have it.
4. **Check.** Run `AWS_PROFILE=<p> aws sts get-caller-identity`. Another account, or an error: go
   back to item 2 of this list. The correct account: continue with **Step 2** below. Put
   `AWS_PROFILE=<p>` before every later `aws` and `mctl` command.
5. **Region.** Run `AWS_PROFILE=<p> aws configure get region`. If it prints nothing, offer
   `aws configure set region <first region> --profile <p>` (ask first: it changes their AWS
   config). If they say no, **Step 4: Plan, ask, apply** sets `AWS_REGION` for the apply.

## Step 2: Check the Multicloud sign-in

Run `mctl auth status`.

- `The sign-in works.` (signed in with the company account) or `The key works.` (API key): continue.
- Not signed in, or the API refused it: ask the user to sign in themselves, in their own
  terminal, then tell you when done:
  `mctl auth login --no-browser`. It prints a link and a code; they open the link in any browser
  (Windows, WSL, SSH and containers cannot open the browser from the terminal), sign in as on
  multicloud.io, and enter the code.
  Or with an API key instead of the company account: on multicloud.io, Account → API keys →
  New key, select **Infrastructure** (if there is no Infrastructure box, Multicloud support
  creates the key), then `mctl auth login --org <org-id> --api-key`. It asks for the key and
  hides it.
  Then run `mctl auth status` again.

`mctl auth status` prints `Organizations:` with the organization IDs of the sign-in. With one
organization, no `--org` is needed. With several, ask the user which one, and add `--org <org-id>`
to every `mctl` command. Do not guess it. For an API key, the user knows the organization ID from
the console (or asks Multicloud support).

## Step 3: Find or create the connection

Run `mctl cloud-account list`.

- The AWS account is listed: note its number (first column). Find its folder (the one with
  `multicloud.tf` whose `account_row_id` is that number). Ask the user if you cannot find it.
  Status `verified`: run `mctl cloud-account verify <n> --wait` and go to step 5 (the user may
  only want the check). Other status: go to step 4.
- Not listed: use the regions the user named. If they named none, ask which regions Multicloud
  may use (it starts machines only there). Name the regions again in the apply question.
- Ask also: "Turn on the AWS opt-in regions in this account?" (default yes). Opt-in regions (for
  example `af-south-1`) are off in a new AWS account. With yes, Multicloud turns them on (only
  the named regions, when the user named some). That takes minutes to hours, and Multicloud never
  turns a region off again.
  - Yes: pass `--opt-in-regions`. No: pass `--no-opt-in-regions`. Always pass one of them: your
    shell has no terminal, and without a flag `mctl` takes yes.
  - The flags need `mctl` 0.4.0 or newer. If `mctl cloud-account create --help` does not list
    them, tell the user that this `mctl` cannot record the choice, and ask them to upgrade
    (`pipx upgrade multicloud-cli`). Do not run `create` without the flag after a "no".
- Ask also: "Allow Multicloud to request higher AWS quotas in this account later, after you approve
  each request?" (default no). Yes lets skill `multicloud-quota` file the requests you approve; no
  means you file them yourself with your own AWS sign-in. Only an organization owner can allow it. Yes: pass
  `--allow-quota-requests`; no: pass `--no-allow-quota-requests`. Always pass one: without a
  terminal, `mctl` takes no. The user can change it later with
  `mctl cloud-account allow-quota-requests <n>`.
- `create` writes `multicloud.tf` into the current directory, and a shell can lose its directory
  between commands, so make the folder and create in one command:

  ```bash
  mkdir multicloud-aws-<account> && cd multicloud-aws-<account> && mctl cloud-account create --cloud AWS --account <12-digit-id> --region <region> [--region <region> ...] <--opt-in-regions | --no-opt-in-regions> <--allow-quota-requests | --no-allow-quota-requests>
  ```

  It prints `Cloud account <n> created ...` and writes `multicloud.tf`. Note `<n>` and the
  absolute path of the folder (`<dir>`). Pass `--dir <dir>` to every `apply` below.

## Step 4: Plan, ask, apply

First make sure Terraform has an AWS region: `multicloud.tf` has no provider block, and without a
region the plan stops with `Error: invalid AWS Region`. If `AWS_REGION` and `AWS_DEFAULT_REGION`
are not set and `aws configure get region` (with the same `AWS_PROFILE`) prints nothing, put
`AWS_REGION=<first region passed to create>` before each `apply` command below. This region only
tells Terraform where to send its calls (the role is global in IAM); Multicloud still uses only the
regions of the connection.

```bash
mctl cloud-account apply <n> --dir <dir> --plan-only
```

Read the plan and tell the user, in a few lines, what it creates in their AWS account:
the role `MulticloudProvisioner-<suffix>`, its policy (EC2 actions, plus read actions on AWS
account regions and Service Quotas and quota requests; creates need the tag `multicloud:managed`),
and the service-linked roles for EC2 Spot, EC2 Fleet and Service Quotas if the account lacks them
(the plan may show these as `aws_cloudformation_stack` resources).
The role suffix is random and is known only after the apply; say `<suffix>`. Report anything else
the plan changes or destroys. `terraform_data.connect` is the step that tells Multicloud the role
exists: on a first apply it is created, on a later apply it is replaced (each apply gets a new
connect code). Both are expected.

Then ask: "Apply this to AWS account <id>?" Only after a clear yes:

```bash
mctl cloud-account apply <n> --dir <dir> --yes
```

This issues the connect code, runs the apply, and waits for the check (up to 15 minutes by
default). Do not interrupt it. If your command tool has a time limit below 20 minutes, add
`--timeout 300`: when the wait ends first, it exits 5, and you continue with
`mctl cloud-account verify <n> --wait --timeout 300`. Repeat it while it exits 5, up to 30
minutes in total, then report "still pending". A new verify needs no new question; a new apply
does.

## Step 5: Report the result

The last lines of `apply` (or of `mctl cloud-account verify <n> --wait`) say what follows. Several
rows can match at once: after `Ready:`, read every `regions` line too and report each one.

| Output | Tell the user | Next |
|---|---|---|
| `Ready: AWS account <id> is connected (policy version <v>).` (exit 0) | The account is ready. | Done. |
| `regions ENABLING  <regions>` and `Turning on N opt-in regions takes minutes to hours. Verify again to add them to Multicloud.` | AWS is turning those regions on. Multicloud uses them only after a new verify. | Tell the user to run `mctl cloud-account verify <n>` later (or offer to, when they ask), for example in an hour. |
| `regions SKIPPED   <regions> (you chose to leave them off)` | Those opt-in regions stay off by the user's choice. | Nothing. To change the choice: `mctl cloud-account verify <n> --opt-in-regions` (ask first). |
| `regions SKIPPED   <regions> (not in the allowed regions)` | Those opt-in regions are outside the regions of the connection, so Multicloud may not turn them on. | Nothing. To use one, the connection needs that region in `regions` (a new apply, with a new question). |
| `regions WARNING   The role has policy version ...` | The role comes from an older module, so Multicloud cannot turn on regions. The account still works. | Offer to change the module version in `multicloud.tf` to the version the warning names (2.0.0 today; it needs OpenTofu or Terraform 1.10) and apply again (step 4, with a new question). The plan must not destroy the existing service-linked roles: if it does, stop and ask. |
| `regions WARNING   AWS denied account:...` | An SCP (service control policy) or the role policy blocks the region calls. The account still works. | If the module is current, an SCP is likely: the user's AWS administrator must allow `account:ListRegions` and `account:EnableRegion`, or turn the regions on in the AWS console. |
| `Missing permissions:` and a list (exit 1) | The exact permissions. Usually someone changed the role policy, or an SCP (service control policy) blocks an action. | Offer to apply again (step 4, with a new question). If it fails again with the same list, an SCP is likely: the user's AWS administrator must allow those actions. |
| `Still pending after ...` (exit 5) | AWS has not finished the IAM change. | Run `mctl cloud-account verify <n> --wait` again later. |
| An `Error:` line and exit 3 (a `list`, `create` or `apply` refused with 403) | The sign-in may not connect cloud accounts: only the organization owner, or an **Infrastructure** API key, can. | The organization owner signs in, or the user stores an Infrastructure key (step 2). |
| `Verification failed` with `Reason: ACCOUNT_NOT_DEDICATED` | The AWS account already holds other work. Multicloud recommends an account made only for Multicloud. | Ask: a new AWS account (skill `multicloud-aws-account-setup`), or connect this one as shared. Shared: the **organization owner** runs `mctl cloud-account accept-shared-account <n>` in their own terminal and types the 12-digit AWS account ID (it has no `--yes`: the typed ID is the approval, so never run it for them). It prints `Ready: ... connected as a shared account` and the quota lines. |
| `ACCOUNT_HELD` (in an `Error:` line, or in the API answer the apply prints) | Another Multicloud organization connected this AWS account. | Stop. The user contacts Multicloud support. |
| `ROLE_ARN_MISMATCH` | The AWS login was in another account. | Back to step 1. |
| `CONNECT_TOKEN_GONE` | The code expired or was used. | Run step 4 again; apply gets a new code. |
| Any other error | Quote the error line. | Do not retry more than once without the user. |

`mctl cloud-account show <n>` gives the details (status, account, regions, role, policy version,
last check) if the user asks.

## Disconnect

Only on an explicit request, and in this order:

1. Ask, then run `mctl cloud-account disconnect <n> --wait --yes` (needs the organization owner's
   sign-in, not an API key; `--yes` only after the user's clear yes, because your shell has no
   terminal). Multicloud stops its machines, deletes what it created in the account, and disables
   the pools that use it. Wait for the status `revoked`; report any `leftovers` it lists.
2. Then ask, and run `tofu destroy` (or `terraform destroy`) in the connection folder. It deletes
   the role, after which Multicloud cannot use the account.

A `destroy` before step 1 can leave machines running and billed that Multicloud can no longer reach.

## Hand back

End with one line, so an onboarding flow can continue (IDs and states only):

```text
MULTICLOUD-RESULT skill=multicloud-connect-aws status=<done|waiting|blocked|failed> cloud_account_id=<n> aws_account_id=<id> connection_dir=<absolute path> quota_low=<none|comma-separated quota LOW lines> quota_requests_allowed=<yes|no>
```

`waiting`: still pending, or regions ENABLING. `blocked`: `who=owner` (exit 3), `who=aws-admin` (an
SCP blocks), `who=multicloud-contact` (`ACCOUNT_HELD`).

The file `flows/connect.json` next to this file holds the same connection as steps for a person who
works without an agent (the printed PoC page). You follow this file, not the flow file.
