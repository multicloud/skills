---
name: multicloud-aws-account-setup
description: Use when someone has a brand-new AWS account (only the root login), has no AWS identity that can create IAM roles, does not know how to enable AWS single sign-on (IAM Identity Center), needs an IAM user and CLI access key, or cannot sign in to AWS from the terminal ("aws configure sso", "aws configure", AWS profile) before connecting AWS to Multicloud.
---

# Set up an AWS account and the AWS CLI sign-in

You give the user an AWS identity that is not the root user and can create IAM roles, and a
working AWS CLI profile. The steps, with the exact clicks, are in `flows/aws-account-setup.json`
next to this file (stage `aws-account`: root MFA, path A, path B; stage `aws-cli-signin`).
Follow them in the order of this file. The `who_kind` field of a step says who does it:

| `who_kind` | You |
|---|---|
| `browser` | Guide the user click by click, or drive the AWS console if you have browser tools. The user types passwords and MFA codes. |
| `user` | The user does it alone. Tell them what to do; wait for "done". |

## Rules that do not bend

1. **Never use the root user** for anything but the steps of stage `aws-account` (root MFA, turning
   on IAM Identity Center or creating the IAM user). Never create root access keys.
2. **Never see an AWS secret.** The "Retrieve access keys" page (path B) shows the secret once: the
   user does that page alone, with no screenshot and no page read by you. The user types the key into
   `aws configure` in their own terminal. If the user pastes a key in the chat, tell them to
   deactivate and delete it on the same IAM page and make a new one.
3. Never read `~/.aws/credentials` or `~/.aws/sso/cache`, never run `aws configure
   export-credentials`, `aws configure get aws_secret_access_key` or `aws sts get-session-token`.
4. **Never type into a password or MFA field**, and ask before you accept AWS terms or create an AWS
   organization.

## Step 0: Dedicated sub-account (preferred)

Policy: Multicloud runs in a **separate AWS account** for the PoC. Offer this first, before any
existing account is used. Explain in one line: "A new account keeps the PoC apart from your current
work, and you can close it later."

- **Using AWS Organizations** (the management account of the organization): the product's own path
  is the one in the Multicloud console (`content/docs/connect-aws.md` in the `website` repo, section
  "Connect a new AWS account"):
  1. First ask the questions of `multicloud-connect-aws`, Step 3, one at a time: regions (default: all;
     pass `--region` only when the user limits them), opt-in regions (default yes), and quota requests by Multicloud (recommend yes; each
     filing still needs a yes). Pass the answers as flags; without a terminal `mctl` takes no for
     quota requests:
     `mctl cloud-account create --cloud AWS --new-account-email <email> [--region <r> ...]
     <--opt-in-regions | --no-opt-in-regions> <--allow-quota-requests | --no-allow-quota-requests> --org <org>`
     with a new email that no AWS account uses (a plus address such as `you+multicloud@…` usually
     works). Type the email twice; a typo creates an account with the wrong email. This writes
     `multicloud.tf` and `multicloud.auto.tfvars` in the folder (keep both).
  2. In that folder, with the **management account's** profile (for example `AWS_PROFILE=<mgmt>
     AWS_REGION=us-east-1`), run `mctl cloud-account apply <n> --plan-only`. It shows the plan of
     the new AWS account (the role plan can show only after the account exists). Show the plan
     counts, then ask one yes/no that names both changes: "Create AWS account <email> and the
     Multicloud role in it?"
  3. After the yes: `mctl cloud-account apply <n> --yes`. It creates the AWS account (a few
     minutes), then the role, and waits until Multicloud verifies the account. mctl gives OpenTofu
     the connect token in the environment of that one process; nobody sees or pastes it. Do not run
     `tofu apply` by hand here: without the token, OpenTofu asks for `var.multicloud_connect_token`.
  4. Multicloud gets no access to the management account. Only the user's Terraform run uses it.
  If the CLI and the website differ, the website is the product's current path: check it first.
- **Without an organization:** the user creates a new AWS account with a new email address
  (aws.amazon.com → Create an AWS account), then continues with Step 1 in that account.

Ask before you create anything: an organization, an account, or Terraform apply. The account's
billing is the user's. Then carry the new account ID into `multicloud-connect-aws` as
`aws_account_choice=new`.

If the user wants to keep an existing account, skip Step 0 and stop before Step 1: the user must
approve the warning in `multicloud-connect-aws`, Rule 6, first.

**When the current sign-in cannot create IAM roles (tested 2026-11-16: `SystemAdministrator` was
denied `iam:CreateRole`):** the fix is not a different role on the same account. Ask the person who
holds the **root login or administers the AWS Organization** (the management account) to:

1. Create the member account (Organizations → Add an account), named for the PoC, with an email they
   own.
2. In IAM Identity Center, assign a role with full administrator rights to the user for that new
   account.

Then the user runs `aws configure sso` with a new profile for that new account, and Step 3 continues.
Rules: the root login is used only by its holder, and only for these steps. Never give the root
login or its keys to this agent, to Multicloud or to the user's AI tool. The agent does not
create accounts with root.

## Step 1: Choose the path

First ask: "Can you sign in to this AWS account with an identity that is not the root user and can
create IAM roles?" Yes: skip to **Step 3** (only the CLI sign-in).

Else ask which path (one question):

| Path | For | Result |
|---|---|---|
| **A: IAM Identity Center** (recommended for a team) | Several people, single sign-on, no long-lived key | A user with `AdministratorAccess`, and the AWS access portal URL |
| **B: IAM user with an access key** (faster) | One person, a short PoC | User `poc-admin` with `AdministratorAccess`, and one CLI access key to delete after the PoC |

Recommend by the answer to one more question, "Is this account only for a short test by you
alone?": yes → path B (fewer steps; delete the key at the end); no, or the account stays → path A.
Path A turns on AWS Organizations for the account. Say so in the question: an account that must
stay outside an organization takes path B.

## Step 2: Set up the account (stage `aws-account`)

1. Step `protect-root` first, on both paths: MFA on the root user.
2. Path A: steps `a1-…` to `a4-…`. Ask for the **Identity Center region** and the **AWS access
   portal URL** (neither is secret).
3. Path B: steps `b1-iam-user`, then `b2-access-key` (the user alone).
4. The user signs out of the root user.

## Step 3: CLI sign-in (stage `aws-cli-signin`)

Before the user starts, tell them every question the command asks and the answer to give. Do not
wait for them to get stuck:

1. **SSO start URL** (path A): the AWS access portal address, like
   `https://d-1234567890.awsapps.com/start`. Where: the AWS console, search **IAM Identity Center**,
   copy **AWS access portal URL** on the dashboard. No IAM Identity Center in that account yet: stop
   and go back to Step 2 (path A).
2. **SSO region** (path A): the region where IAM Identity Center is turned on. Where: the region
   selector at the top right of the IAM Identity Center console. Often `us-east-1`.
3. **Account** (path A): for a new account that Multicloud's Terraform creates (Step 0), the
   **management account** of the AWS Organization. Otherwise the account the user chose in Step 0 or
   Step 1. **Stop here if it is an existing account** that was not approved under
   `multicloud-connect-aws`, Rule 6.
4. **Role**: choose `AdministratorAccess`, or another role that can create IAM roles. Not
   `SystemAdministrator`: it was denied `iam:CreateRole` (tested 2026-11-16). Check the name you
   see in the list. Never the
   root login; Multicloud does not use it. No admin role listed: stop and ask the user's AWS
   administrator (`status=blocked who=aws-admin`). After sign-in, the ARN shows the role name
   (`AWSReservedSSO_<role>_…`).
5. **Default client region**: `us-east-1` (the region the PoC uses).
6. **Default output format**: `json`.
7. **Profile name**: `poc`. Other prompts (session name, registration scopes): press Enter for the
   default.

The user runs the command in their own terminal (on Windows: the WSL window of the `wsl_distro`), because it asks
questions you cannot answer for them. Tell them each answer from the flow step:

- Path A, or any single sign-on: `aws configure sso --use-device-code` (the flow's command; it
  prints a link and a code, which works on every machine, WSL and SSH included). AWS CLI 2.22 or
  later; an older CLI rejects the flag and already uses a device code, so run it without the flag.
- Path B, or an existing IAM user key: `aws configure --profile poc`.
- Profile name: one that `aws configure list-profiles` does not list yet (an existing name is
  overwritten). The flow uses `poc`.

Then you run:

```bash
AWS_PROFILE=poc AWS_PAGER= aws sts get-caller-identity --query '[Account,Arn]' --output text </dev/null
```

- The ARN ends in `:root`: the profile signs in as root. Stop, go back to Step 1.
- An error: path A, the user runs `aws sso login --profile poc` (on WSL with
  `--use-device-code`) and you check again.
- The account ID differs from the one the user named: stop and ask.

## Later

- A path A sign-in expires after some hours: the user runs `aws sso login --profile <p>`.
- Path B: at the end of the PoC, the user deletes the key: IAM › Users › `poc-admin` › Security
  credentials › the key › Actions › Deactivate, then Delete. Ask before you guide this.

## Hand back

```text
MULTICLOUD-RESULT skill=multicloud-aws-account-setup status=done aws_account_id=<12 digits> aws_profile=<p> aws_path=<A|B|existing> sso_region=<r|none> path_b_key=<yes|no>
```

`status=blocked who=aws-admin` when the user has no identity that can create IAM roles and cannot
make one (a company account): their AWS administrator must give them one.
