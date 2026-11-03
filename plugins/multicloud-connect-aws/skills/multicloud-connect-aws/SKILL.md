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

## Step 1: Check the tools

Run these and report what is missing, with the install line:

| Check | If missing |
|---|---|
| `mctl --version` | `pipx install multicloud-cli` (or `uv tool install multicloud-cli`) |
| `tofu version` or `terraform version` (1.5 or later; `mctl` uses `tofu` when both exist) | OpenTofu: https://opentofu.org/docs/intro/install/. An older version: stop and ask the user to upgrade. |
| `aws sts get-caller-identity` | Fails, shows another account, or the user does not know their AWS profile: follow **AWS sign-in help** below. If they use a profile, use `AWS_PROFILE=<p>` in later commands. |

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
   No AWS login at all, or no role that can create IAM roles: their AWS administrator must give
   them one. Stop until they have it.
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
  `mctl auth login`. It opens the browser; they sign in as on multicloud.io.
  With no browser (SSH, a container): `mctl auth login --no-browser`.
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
  may use (it starts machines only there). Name the regions again in the apply question. `create`
  writes `multicloud.tf` into the current directory, and a shell can lose its directory between
  commands, so make the folder and create in one command:

  ```bash
  mkdir multicloud-aws-<account> && cd multicloud-aws-<account> && mctl cloud-account create --cloud AWS --account <12-digit-id> --region <region> [--region <region> ...]
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
the role `MulticloudProvisioner-<suffix>`, its policy (EC2 actions only, creates need the tag
`multicloud:managed`), and the EC2 Spot and Fleet service-linked roles if the account lacks them.
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

The last lines of `apply` (or of `mctl cloud-account verify <n> --wait`) say:

| Output | Tell the user | Next |
|---|---|---|
| `Ready: AWS account <id> is connected (policy version <v>).` (exit 0) | The account is ready. | Done. |
| `Missing permissions:` and a list (exit 1) | The exact permissions. Usually someone changed the role policy, or an SCP (service control policy) blocks an action. | Offer to apply again (step 4, with a new question). If it fails again with the same list, an SCP is likely: the user's AWS administrator must allow those actions. |
| `Still pending after ...` (exit 5) | AWS has not finished the IAM change. | Run `mctl cloud-account verify <n> --wait` again later. |
| An `Error:` line and exit 3 (a `list`, `create` or `apply` refused with 403) | The sign-in may not connect cloud accounts: only the organization owner, or an **Infrastructure** API key, can. | The organization owner signs in, or the user stores an Infrastructure key (step 2). |
| `ACCOUNT_HELD` (in an `Error:` line, or in the API answer the apply prints) | Another Multicloud organization connected this AWS account. | Stop. The user contacts Multicloud support. |
| `ROLE_ARN_MISMATCH` | The AWS login was in another account. | Back to step 1. |
| `CONNECT_TOKEN_GONE` | The code expired or was used. | Run step 4 again; apply gets a new code. |
| Any other error | Quote the error line. | Do not retry more than once without the user. |

`mctl cloud-account show <n>` gives the details (status, account, regions, role, policy version,
last check) if the user asks.

## Disconnect

Only on an explicit request. First the user tells Multicloud support, so that Multicloud stops its
machines in the account (a self-service disconnect is planned); a `destroy` before that can leave
machines running and billed that Multicloud can no longer reach. When support confirms, tell the
user that `tofu destroy` (or `terraform destroy`) in the connection folder deletes the role, after
which Multicloud cannot use the account. Ask before you run it.
