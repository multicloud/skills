# Windows live run: `multicloud-onboarding`, door Extend (GPU)

Status: **in progress, paused at the WSL hand-off.** No cloud resources were created.
Machine: Windows 10 Home 10.0.19045 (the checklist assumed Windows 11).
Claude Code 2.1.325. Branch `claude/multicloud-onboarding`, PR 7 still a draft; not merged.

## Results so far

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 0 | Agent is on Windows | PASS | `$env:OS` = `Windows_NT`; PowerShell 5.1.19041. `uname` not present, which is expected in PowerShell. |
| 1 | OS detection gives `run_prefix=wsl`; WSL2 Ubuntu check | PARTIAL | The detection rule in `multicloud-workstation` gives `run_prefix=wsl` for a Windows host shell. The WSL check failed: no Ubuntu distro is registered (`HKCU:\...\Lxss` is empty) and the WSL Store app is not installed. `wsl.exe -l -v` and `wsl.exe --status` both print the usage text (see issue 3). The `windows` stage hand-off to Yaron is in progress. |
| 2 | Every command via `wsl.exe -d Ubuntu -- bash -lc` | NOT REACHED | No WSL command run yet. |
| 3 | Ledger in WSL home, mode 600 | NOT REACHED | No ledger yet; the ledger is created in Step 1 of the orchestrator, after WSL. |
| 4 | Tool installs in WSL | NOT REACHED | Needs Ubuntu. |
| 5 | `mctl auth login --no-browser` from WSL | NOT REACHED | Needs `mctl`. |
| 6 | `aws configure sso --use-device-code` from WSL | NOT REACHED | Needs `aws`. |
| 7 | `connect-aws` with module 2.0.0 | NOT REACHED | |
| 8 | Quota check / request | NOT REACHED | |
| 9 | Extend: cluster, GPU pool, peering, vLLM, `/health` | NOT REACHED | |
| 10 | Cleanup | NOT REACHED | No cloud resources exist yet. |

Plugin setup (checklist step 4): PASS. The marketplace `multicloud` was added from the local clone, and all 7 `multicloud-*` plugins installed and are enabled. The skills were not visible until Claude Code was restarted.

## Hand-off to Yaron (required before the run continues)

In an **administrator** PowerShell, run:

```powershell
wsl --install -d Ubuntu
```

Restart Windows. Then open Ubuntu once and set a Linux user name and password. Then come back to this session and say: "continue my Multicloud onboarding."

## Issues found and changes needed in the skills

1. **Checklist says Windows 11; the test machine is Windows 10 Home.** `windows11-checklist.md` should say "Windows 10 (2004+) or Windows 11". `multicloud-workstation` already allows 10 and 11.
2. **`irm` is not a Command Prompt command.** The checklist showed `irm` without saying it needs PowerShell. Fixed in the checklist (`c8bcb94`): cmd.exe note and the `install.cmd` alternative.
3. **`wsl.exe -l -v` prints usage on this machine.** The inbox `C:\Windows\System32\wsl.exe` (10.0.19041) rejects `-l -v` and `--status`, because the WSL Store app is not installed. `multicloud-workstation/SKILL.md` Step 1 and the orchestrator's Step 1 say to read `wsl.exe -l -v` for "Ubuntu with VERSION 2". On a machine like this, that output is not a distro list, so the check is ambiguous. Proposed fix: check with `Get-CimInstance Win32_OptionalFeature -Filter "Name='Microsoft-Windows-Subsystem-Linux'"` (InstallState 1 = enabled, 2 = disabled) and the `HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss` distro list, and treat "usage text" as "no WSL Store app". Also say that `wsl --install -d Ubuntu` installs the Store WSL.
4. **Restart after installing plugins.** The skill list is fixed when a session starts. The `multicloud-*` skills were missing until a restart, and the orchestrator was not usable before it. Add to the checklist: after the plugin install, restart Claude Code (`claude --continue`). Proposed fix in the checklist, step 4.
5. **Marketplace add needs a quoted path.** `claude plugin marketplace add "$PWD"` works in PowerShell with spaces in the path (`C:\Users\Yaron Rosenbaum\...`). The checklist uses `"$PWD"`, which is correct; no change needed.
6. **`Get-AppxPackage` does not take an array for `-Name`.** Not a skill issue; noted because it cost a command. The skill should not depend on it.
7. **Workstation `windows` stage is entirely user-only.** Expected, and it matches the rules. The orchestrator says to stop there, which is what happened.

## Changes made on the branch in this run

- `evals/onboarding/windows11-checklist.md`: cmd.exe vs PowerShell note (`c8bcb94`).
- This file (`evals/onboarding/windows11-run.md`): the run log.
- Skill fix for item 4 (restart Windows, then restart Claude Code, and the restart rule after plugin installs): `ee9666e` in the original history, now `71d650d` after the author fix. Orchestrator and `multicloud-workstation` Step 1.
- Skill fix for item 3 (WSL check treats usage text as "no distro" and names the two PowerShell checks): committed on this branch with the same restart and author update. Orchestrator and `multicloud-workstation` Step 1.
- Item 1 (checklist says Windows 11): fixed. The checklist now says "Windows 10 2004+ or Windows 11".
- Item 11 (asked by the user, option 2): the skills hardcoded `wsl.exe -d Ubuntu` in about a dozen places, so only Ubuntu worked. Fixed: every command uses `<wsl_distro>`, which the agent picks from `wsl.exe -l -v` (VERSION 2) and records in the ledger. Ubuntu is still the default. Changed in `multicloud-workstation`, `multicloud-onboarding`, `multicloud-extend`, `multicloud-connect-aws` and `multicloud-aws-account-setup`. The flow JSON still names Ubuntu in its install step and the "open Ubuntu" step; that is the default, not a requirement.
- Item 10 (found by the check): `Get-WindowsOptionalFeature` fails without an elevated shell ("requires elevation") and takes one feature name per call. The skill's check used it, and the flow's restart reason assumed the features were off. Fixed: the check uses `Get-CimInstance Win32_OptionalFeature` (no admin). Live result on this PC before the install: `VirtualMachinePlatform` = 2 and `Microsoft-Windows-Subsystem-Linux` = 2, and in `Win32_OptionalFeature` 2 means **disabled** (1 = enabled). My earlier reading that both were on was wrong. `wsl --install -d Ubuntu` (elevated, approved on screen) installed both features and exited 1 with "Catastrophic failure"; afterwards `VirtualMachinePlatform` = 1. The features need a restart before a distro can start, and no distro is registered yet.
- Item 9 (asked by the user): the skills suggested steps without checking the computer first. Fixed: a "check before you suggest" rule in both `multicloud-workstation` and the orchestrator; each step names its read-only check.
- Item 8 (asked by the user): the restart reason was missing from the skill, and the flow said "you cannot do this" about PowerShell. Fixed in `multicloud-workstation`: the reason is written in the flow and SKILL.md; the agent runs the read-only checks and, after a yes, the install from an elevated PowerShell (UAC prompt approved by the user); a restart waits for a yes and follows a ledger save.
- Author of the unpushed commits: GitHub blocked pushes that publish `yaron.rosenbaum@gmail.com` (GH007). The commits were reset to `Claude <noreply@anthropic.com>`, the author of earlier commits on this branch, before pushing `c8bcb94..3dea5a1`.
