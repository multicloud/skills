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

## Step 1: Choose the path

First ask: "Can you sign in to this AWS account with an identity that is not the root user and can
create IAM roles?" Yes: skip to **Step 3** (only the CLI sign-in).

Else ask which path (one question):

| Path | For | Result |
|---|---|---|
| **A: IAM Identity Center** (recommended for a team) | Several people, single sign-on, no long-lived key | A user with `AdministratorAccess`, and the AWS access portal URL |
| **B: IAM user with an access key** (faster) | One person, a short PoC | User `poc-admin` with `AdministratorAccess`, and one CLI access key to delete after the PoC |

Path A turns on AWS Organizations for the account. Say so in the question: an account that must
stay outside an organization takes path B.

## Step 2: Set up the account (stage `aws-account`)

1. Step `protect-root` first, on both paths: MFA on the root user.
2. Path A: steps `a1-…` to `a4-…`. Ask for the **Identity Center region** and the **AWS access
   portal URL** (neither is secret).
3. Path B: steps `b1-iam-user`, then `b2-access-key` (the user alone).
4. The user signs out of the root user.

## Step 3: CLI sign-in (stage `aws-cli-signin`)

The user runs the command in their own terminal (on Windows: the Ubuntu window), because it asks
questions you cannot answer for them. Tell them each answer from the flow step:

- Path A, or any single sign-on: `aws configure sso`. If no browser opens (WSL, SSH), the user
  presses Ctrl+C and runs `aws configure sso --use-device-code`.
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
