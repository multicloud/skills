---
name: multicloud-workstation
description: Use when someone must prepare their computer for Multicloud - install mctl (the Multicloud CLI, package multicloud-cli), the AWS CLI, OpenTofu, kubectl, helm or jq, set up WSL2 on Windows, create a multicloud.io account and organization, sign in with "mctl auth login", or connect an AI agent to the Multicloud MCP server.
---

# Prepare the computer for Multicloud

You make the user's computer ready: on Windows a Linux shell (WSL2), a multicloud.io account, the
command-line tools, and the Multicloud sign-in. The steps, with the exact commands per system, are
in `flows/workstation.json` next to this file. Follow them in the order of this file.

## Rules that do not bend

1. **The user types every password and code.** Linux password, `sudo` password, multicloud.io
   password, MFA codes. You never see them.
2. **Never handle a Multicloud API key.** The new-key page on multicloud.io shows the key once: the
   user does that page alone, and puts the key into their AI tool's settings themselves. If the
   user pastes a key, tell them to revoke it (Account › API keys) and make a new one.
   `mctl auth login` (browser sign-in) needs no key: prefer it.
3. **Never store a key in a lasting setting** (`setx`, `~/.bashrc`, `~/.zshrc`, a `.env` file).
4. **Check before you suggest.** Before you suggest any install, restart, sign-in or command,
   run its read-only check on this computer and suggest only what is missing or wrong. Examples:
   `Get-WindowsOptionalFeature` and `wsl.exe -l -v` (WSL), `mctl --version`, `aws --version`,
   `tofu version`, `kubectl version --client`. Say what you found ("Ubuntu is not installed",
   "mctl 0.x is installed") before you suggest the next step.
5. **Ask before you install.** Name the tools and the commands in one question. A yes covers that
   list.

## How to read the flow file

Each stage has `steps`. Each step has `h` (title), `d` (what to do), `in` (values the user enters),
`c` (one command block) or `os` (`mac`, `linux`, `win` blocks), `g` (a note), and `who_kind`:

| `who_kind` | You |
|---|---|
| `agent` | Run it. It changes nothing outside the working folder. |
| `ask` | Show the command and ask; run it after a yes. On Windows, the agent can run PowerShell itself (checks, install, restart); each change waits for a yes, and an admin install needs the user to approve the Windows admin prompt (UAC). |
| `browser` | Guide the user click by click, or drive the browser if you have browser tools. The user types passwords and codes. |
| `user` | The user does it alone (a secret, an admin right, a reboot). Tell them what to do, wait for "done". |
| `page` | A line for the printed page only. Skip it. |

A `win` block runs inside Ubuntu (WSL2), never in PowerShell.

## Step 1: Find the system

Run `uname -s` alone (no `||` and no `/dev/null`: Windows PowerShell 5.1 rejects both).

| Result | System | `run_prefix` |
|---|---|---|
| `Darwin` | macOS | `none` |
| `Linux`, and `uname -r` contains `microsoft` | Windows, you are already inside WSL | `none` |
| `Linux` | Linux | `none` |
| `MINGW…`, `MSYS…`, `CYGWIN…`, or an error such as "not recognized" (PowerShell, cmd) | Windows host shell | `wsl` |

`run_prefix=wsl` means: wrap every command as `wsl.exe -d <wsl_distro> -- bash -lc '<command>'`,
where `<wsl_distro>` is the WSL2 distro the user has (Ubuntu by default; any WSL2 distro works, for
example Debian). Record it in the ledger as `wsl_distro`. Never hardcode a distro name.

On a Windows host shell:
- Check for an Ubuntu WSL2 distro. Run `wsl.exe -l -v`. If it prints a distro list, use it. If it
  prints usage text (`Usage: wsl.exe`), the WSL Store app is missing (the old inbox binary runs
  instead), so treat it as "no distro". Confirm in PowerShell: the optional feature
  `Get-CimInstance Win32_OptionalFeature -Filter "Name='Microsoft-Windows-Subsystem-Linux'"`
  (InstallState 2 = enabled) and the registered distros under
  `HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss` (empty = none).
- No Ubuntu with VERSION 2: do stage `windows`. You can run PowerShell yourself, but every change
  waits for the user's yes: first the read-only checks (`Get-CimInstance Win32_OptionalFeature` for
  `VirtualMachinePlatform` and `Microsoft-Windows-Subsystem-Linux`; `Get-WindowsOptionalFeature`
  needs an elevated shell and takes one name per call, so do not use it for checks), then the
  install. If both features are already on (InstallState 2), no feature restart is needed: say so
  and only the Ubuntu install and its first start are left. The install
  needs administrator rights: start an elevated PowerShell (`Start-Process powershell -Verb RunAs`)
  and let the user approve the Windows admin prompt (UAC) on their screen; never type or pass the
  user's password. Why a restart: when `wsl --install` turns on a Windows feature (the Linux subsystem or
  Virtual Machine Platform, which run the WSL2 Linux kernel), Windows loads it only at boot. If the
  checks show both features on, there is no such reason.
  Ask before the restart, save the ledger first, then tell the user: after the restart, open Ubuntu
  once and set a Linux user name and password, then restart Claude Code (`claude --continue`) so the
  Multicloud skills load. A restart ends this session, so the next session resumes from the ledger.
  A company policy that blocks WSL: stop with `status=blocked who=it`.
- Run every later command as `wsl.exe -d <wsl_distro> -- bash -lc '<command>'`. For more than one
  line, write the lines to a script inside WSL (`~/multicloud-onboarding/run/<step>.sh`, by a
  heredoc in the same wrapper) and run `wsl.exe -d <wsl_distro> -- bash -l ~/multicloud-onboarding/run/<step>.sh`.
  This avoids PowerShell quoting.
- Keep every file inside the WSL home folder (`~/…`), never under `/mnt/c/…`: Windows ignores
  `chmod 600` there.
- The user's terminal is the **WSL** window of their distro (Ubuntu, Debian, ...). When a step says
  "in your own terminal", it means that window.
- Pick the distro: list the WSL2 distros with `wsl.exe -l -v` (VERSION must be 2). If one or more
  exist, ask the user which to use (default: Ubuntu if it is there), and record it as `wsl_distro`.
  Pass that name to every later command. If none exist, do the install step.

## Step 2: Multicloud account (stage `multicloud-account`)

Skip if the user already has one. The user registers at multicloud.io, verifies the email and
creates the organization (they become its owner). Ask for the **organization ID** (the short name;
it is not secret).

## Step 3: Tools (stage `tools`)

Check first, install only what is missing:

| Check | Need |
|---|---|
| `mctl --version` | any; the newest is best (`uv tool upgrade multicloud-cli`) |
| `aws --version` | starts with `aws-cli/2` |
| `tofu version` or `terraform version` | 1.10 or later (the AWS module 2.0.0 needs it) |
| `kubectl version --client` | Extend only |
| `helm version` | 3.14 or later, Extend only |
| `jq --version` | Extend only |

Use the block of the user's system from the flow. A block with `sudo` asks for a password, which
your shell cannot type: run `sudo -n true` first. It fails: give the block to the user to run in
their own terminal, and wait for "done". `brew` needs no `sudo`. After `uv tool update-shell`, a new
shell is needed: run the next checks in a new `bash -lc` (or ask the user to open a new terminal).

## Step 4: Multicloud sign-in

The user runs, in their own terminal: `mctl auth login`. It opens the browser.
- No browser opens (WSL, SSH, a container): `mctl auth login --no-browser`. It prints a link and a
  code; the user opens the link in any browser.

Then you run `mctl auth status`. `The sign-in works.` and an `Organizations:` line: note the
organization ID. Several organizations: ask which one, and add `--org <id>` to every later `mctl`
command. Connecting a cloud account and allowing quota requests need the **organization owner**;
an exit code 3 on those steps later means this sign-in is not the owner.

## Step 5: Connect the AI (stage `connect-ai`, optional)

Only when the user wants their AI to use the Multicloud MCP server (`https://mcp.multicloud.io/mcp`).
`mctl` covers every onboarding step without it. The user makes the API key and puts it into their
AI tool's MCP settings themselves (step `create-api-key` is `user`). You may show the JSON shape
from the flow, with `mca_…` as the placeholder, never a real key.

## Hand back

```text
MULTICLOUD-RESULT skill=multicloud-workstation status=done os=<macos|linux|windows> run_prefix=<none|wsl> org_id=<id> tools=mctl,aws,tofu[,kubectl,helm,jq]
```

Use `status=blocked who=it` (WSL blocked), `who=user` (waiting for a manual step), or
`status=failed` with the error line.
