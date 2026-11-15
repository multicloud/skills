# Windows 11 live run: prep and checklist

Live test of the `multicloud-onboarding` skill set on a real Windows 11 PC,
door **Extend** (GPU). Draft PR: https://github.com/multicloud/skills/pull/7,
branch `claude/multicloud-onboarding`. Results go to
`evals/onboarding/windows11-run.md` on the same branch.

## 1. Before the run (Yaron, on the PC)

1. Install Claude Code for Windows (native installer, in PowerShell):

   ```powershell
   irm https://claude.ai/install.ps1 | iex
   ```

   Open a new PowerShell window and check `claude --version`. Sign in with
   `claude` once if asked.

2. Install Git for Windows if `git --version` fails (`winget install Git.Git`).
   Claude Code on Windows uses Git Bash for its own shell tool.

3. Clone the repo on the test branch into a folder of your choice:

   ```powershell
   cd $HOME
   git clone https://github.com/multicloud/skills.git
   cd skills
   git checkout claude/multicloud-onboarding
   git pull
   ```

4. Add the local clone as a plugin marketplace and install the 7 onboarding
   plugins from it (not from GitHub `main`, which does not have them yet):

   ```powershell
   claude plugin marketplace add "$PWD"
   foreach ($p in 'onboarding','workstation','aws-account-setup','connect-aws','quota','extend','ci-pool') {
     claude plugin install "multicloud-$p@multicloud"
   }
   claude plugin list
   ```

   `claude plugin list` must show all 7 `multicloud-*` plugins as enabled. If a
   `multicloud` marketplace from GitHub is already added, remove it first
   (`claude plugin marketplace remove multicloud`) so the local clone wins.

5. Pick the AWS **test** account to use (never production). Have its root or
   admin login and MFA device at hand. You will type every password, MFA code
   and secret yourself.

6. Have the Multicloud login (for `mctl auth login`) at hand.

7. From the `skills` folder, in PowerShell, run `claude --teleport` and pick
   this session. Do not start WSL or install tools beforehand: the run must
   show what the skills do on a fresh-ish PC. (If WSL2 Ubuntu is already
   installed, that is fine; say so at the start.)

## 2. Rules for the run

- The agent invokes skill `multicloud-onboarding`, door **Extend** (GPU), and
  follows the skills exactly. Yaron answers as the customer.
- Yaron types every password, MFA code and secret. The agent never enters
  credentials, never asks for a key in chat, never `setx`es a secret.
- The agent asks before every install and before every step that creates cloud
  resources or costs money.
- A GPU node costs money: keep the run short, and always finish the `cleanup`
  stage, even after a failure (delete peering, pools, cluster as the skill says;
  `mctl pool hibernate` at least).
- No secrets, keys or tokens in any file or message, including the report.

## 3. What the run must prove

Each item is recorded as PASS / FAIL / NOT REACHED with one evidence line.

| # | Check |
|---|-------|
| 0 | Agent is on Windows: `uname -s` fails or prints MINGW/MSYS, or `$env:OS` is `Windows_NT`. |
| 1 | OS detection gives `run_prefix=wsl`; WSL2 Ubuntu check (`wsl.exe -l -v`) and, if missing, the WSL install hand-off to Yaron. |
| 2 | Every command runs through `wsl.exe -d Ubuntu -- bash -lc '…'` or a script under `~/multicloud-onboarding/run/`; no native PowerShell for tool steps; no PowerShell quoting breaks. |
| 3 | The ledger `~/multicloud-onboarding/multicloud-onboarding-state.json` is inside the WSL home, mode 0600, never under `/mnt/c`. |
| 4 | Tool installs in WSL: `uv`, `mctl`, AWS CLI v2, OpenTofu ≥ 1.10, kubectl, helm, jq, unzip; the `sudo -n true` fallback when sudo needs a password. |
| 5 | `mctl auth login --no-browser` works from WSL. |
| 6 | `aws configure sso --use-device-code` works from WSL (flag UNVERIFIED so far), or path B (IAM user) works. |
| 7 | `connect-aws`: consent question, `tofu init/plan/apply` with module 2.0.0, account verified. |
| 8 | Quota check and, if needed, the request with owner consent. |
| 9 | Extend: cluster reachable from WSL, GPU pool, peering bundle saved with mode 600, vLLM pod ready, port-forward `/health` answers from WSL. |
| 10 | Cleanup leaves no pool, peering or GPU node running. |

Also recorded: each skill's `MULTICLOUD-RESULT skill=… status=…` line, and
every skill text bug found, with `file:line`. Clear text bugs are fixed on the
branch, one commit each, and listed in the report. PR 7 is not merged.
