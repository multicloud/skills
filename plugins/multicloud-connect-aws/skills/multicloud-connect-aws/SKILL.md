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
   multicloud.io (Account → API keys) and make a new one. The user stores the key themselves with
   `mctl auth login` in their own terminal.
2. **Never handle the connect code.** Do not run `mctl cloud-account token` (it prints the code;
   that command is for people who apply by hand). `mctl cloud-account apply` gets the code and
   gives it to Terraform without showing it. Never read `~/.config/multicloud/credentials`, never
   run `mctl cloud-account show --json` piped into other tools to look for secrets, never print
   environment variables.
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
| `tofu version` or `terraform version` (1.5 or later) | OpenTofu: https://opentofu.org/docs/intro/install/ |
| `aws sts get-caller-identity` | The user logs in to AWS their usual way (for example `aws sso login --profile <p>`). If they use a profile, use `AWS_PROFILE=<p>` in later commands. |

Tell the user the AWS account ID that `aws sts get-caller-identity` shows. It must equal the
account they want to connect. If it differs, stop and ask them to log in to the correct account.
The login must be able to create IAM roles and policies.

## Step 2: Check the Multicloud key

Run `mctl auth status`.

- `The key works.`: continue.
- No key, or the API refused it: ask the user to do this themselves, then tell you when done:
  1. On multicloud.io, open Account → API keys → New key, select **Infrastructure**, create it,
     copy it. (If there is no Infrastructure box, Multicloud support creates the key.)
  2. In their own terminal: `mctl auth login --org <team-id>`. It asks for the key and hides it.
  Then run `mctl auth status` again.

If the user does not know the team ID, they ask Multicloud support. Do not guess it.

## Step 3: Find or create the connection

Run `mctl cloud-account list`.

- The AWS account is listed: note its number (first column). Find its folder (the one with
  `multicloud.tf` whose `account_row_id` is that number). Ask the user if you cannot find it.
  Status `verified`: go to step 5 (the user may only want the check). Other status: go to step 4.
- Not listed: use the regions the user named. If they named none, ask which regions Multicloud
  may use (it starts machines only there). Name the regions again in the apply question. Make a new, empty folder (for example `multicloud-aws-<account>`), go into it, and run:

  ```bash
  mctl cloud-account create --cloud AWS --account <12-digit-id> --region <region> [--region <region> ...]
  ```

  It prints `Cloud account <n> created ...` and writes `multicloud.tf`. Note `<n>`.

## Step 4: Plan, ask, apply

In the connection folder:

```bash
mctl cloud-account apply <n> --plan-only
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
mctl cloud-account apply <n> --yes
```

This issues the connect code, runs the apply, and waits for the check (up to 15 minutes by
default). Do not interrupt it. If your command tool has a time limit below 20 minutes, add
`--timeout 300`: when the wait ends first, it exits 2, and you continue with
`mctl cloud-account verify <n> --wait --timeout 300` (repeat up to three times). A new verify
needs no new question; a new apply does.

## Step 5: Report the result

The last lines of `apply` (or of `mctl cloud-account verify <n> --wait`) say:

| Output | Tell the user | Next |
|---|---|---|
| `Ready: AWS account <id> is connected (policy version <v>).` (exit 0) | The account is ready. | Done. |
| `Missing permissions:` and a list (exit 1) | The exact permissions. Usually someone changed the role policy, or an SCP (service control policy) blocks an action. | Offer to apply again (step 4, with a new question). If it fails again with the same list, an SCP is likely: the user's AWS administrator must allow those actions. |
| `Still pending after ...` (exit 2) | AWS has not finished the IAM change. | Run `mctl cloud-account verify <n> --wait` again later. |
| `ACCOUNT_HELD` | Another Multicloud team connected this AWS account. | Stop. The user contacts Multicloud support. |
| `ROLE_ARN_MISMATCH` | The AWS login was in another account. | Back to step 1. |
| `CONNECT_TOKEN_GONE` | The code expired or was used. | Run step 4 again; apply gets a new code. |
| Any other error | Quote the error line. | Do not retry more than once without the user. |

`mctl cloud-account show <n>` gives the details (status, account, regions, role, policy version,
last check) if the user asks.

## Disconnect

Only on an explicit request. Tell the user that `tofu destroy` (or `terraform destroy`) in the
connection folder deletes the role, after which Multicloud cannot use the account, and that they
should also tell Multicloud support so it stops its machines there. Ask before you run it.
