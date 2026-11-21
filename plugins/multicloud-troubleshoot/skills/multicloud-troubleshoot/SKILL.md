---
name: multicloud-troubleshoot
description: Use when something in Multicloud Extend or a Multicloud pool does not work and the customer wants to find out why with their own access - a pool slow to wake or stuck WAKING, a pool with no worker, a peering not READY or a failed preflight Job, a missing, NotReady or tainted virtual node, pods Pending on the virtual node, NamespaceOffloading NoClusterSelected, the extend-proxy bridge stuck at 0/1 Ready, a proxy-test that fails, quota too low, a cloud account not verified, or mctl asking for --org. Diagnoses read-only with kubectl, mctl and the AWS CLI, proposes fixes the customer can make, and prepares a support bundle without secrets.
---

# Troubleshoot Multicloud Extend and pools

You find out why Extend or a pool misbehaves, with only the access the customer has:
- `kubectl` on the customer's own cluster,
- `mctl` signed in as the customer (`mctl auth login`),
- the AWS CLI in the customer's own AWS account.

You have no access to Multicloud's side. When a check points there, collect the support bundle
(Step 4) and escalate. The checks, results and fixes are in `playbook.md` next to this file. Use
the commands as written there.

## Rules that do not bend

1. **Read-only by default.** Every check in `playbook.md` reads, except the ones marked "ask":
   they start one short test pod (`udp-check`, `proxy-test`), so ask before them too. A fix changes something: show the
   command, name the cluster (`kubectl config current-context`) or the pool, ask, and run it only
   after a clear yes. A yes covers one fix. Deletes cannot be undone: say so.
2. **No secrets.** Never print, `cat`, copy or ask for the peering bundle (`multicloud-peering.yaml`),
   the bridge key (Secret `extend-proxy-api-key`), the model key, a Multicloud API key (`mca_…`) or
   AWS keys. Check that a secret exists with `kubectl get secret <name> -o name` or `test -s`, never
   with `-o yaml`, `-o json` or `describe`. If the user pastes a secret, tell them to revoke it and
   make a new one.
3. **Never run `mctl peering show` to diagnose.** The first read of a READY peering returns the
   bundle once, and then the bundle is gone. Use `mctl peering list <pool>` (columns STATUS and
   MESSAGE). Run `peering show` only after the bundle is saved (skill `multicloud-extend`, step
   `save-bundle`).
4. **Several organizations.** If `mctl auth status` lists more than one organization, put
   `--org <org-id>` on every `mctl` command, or set `MULTICLOUD_ORG`. Use the same organization for
   every command in one diagnosis. mctl may fall back to a saved organization without an error, and
   then shows empty lists or "not found" for the pool.
5. **Live state wins.** Run the check; do not guess from memory or from an old ledger.
6. **Say what is untested.** A command marked `UNTESTED` in `playbook.md` was not run by the skill
   authors. Run it read-only, and if it fails for syntax, say so and do not improvise a change.

On Windows, run every command inside WSL (`wsl.exe -d <wsl_distro> -- bash -lc '…'`; see skill
`multicloud-workstation`). Keep every file of this skill in the WSL home, never under `/mnt/c`.

## Step 1: Collect the facts (read-only)

Ask for, or take from the onboarding ledger (`~/multicloud-onboarding/multicloud-onboarding-state.json`):
the pool name, the organization ID, the kubeconfig and context, the offloaded namespace (default
`my-apps`), and the cloud-account ID. Then run the triage, in this order, and report each line:

```bash
mctl auth status                     # signed in; lists your organizations
mctl pool show <pool>                # Status, Nodes, Cost per hour
mctl peering list <pool>             # STATUS and MESSAGE of each peering
mctl pool diagnose <pool>            # Multicloud's view: lifecycle, gates, bridge handshakes (mctl 0.13.0+)
kubectl config current-context
kubectl -n liqo get pods             # connector pods Running
kubectl get nodes -l liqo.io/type=virtual-node -L multicloud.io/pool
kubectl -n multicloud-extend-proxy get pods   # bridge, if installed
```

## Step 2: Find the symptom

Match the first bad result to a row. Then open that section of `playbook.md`.

| Symptom | First sign | `playbook.md` section |
|---|---|---|
| mctl stops before any answer | `Your session ended`, `You belong to several organizations`, `You are not a member of` | S1 Sign-in and organization |
| Cloud account not ready | `mctl cloud-account list` STATUS is not `verified`; pool create gives `ACCOUNT_NOT_READY` | S2 Cloud account not verified |
| Not enough AWS quota | pool stays without a GPU worker; `quota-plan` limit below the need | S3 Quota too low |
| Pool wakes slowly or stays waking | `Status: waking` (or `provisioning`) for more than 11 minutes (normal is 8.5 to 11; escalate only after 20) | S4 Pool slow to wake |
| Pool has no worker | `Nodes: 0` while pods wait on the virtual node | S5 Pool has no worker |
| Peering not READY, preflight Job fails | `peering list` STATUS is not `READY`; `kubectl -n liqo wait job/...` times out | S6 Peering and preflight |
| Virtual node missing, NotReady or tainted | no line, `NotReady` or `Unknown`, an unexpected taint | S7 Virtual node |
| Pods Pending on the virtual node | `kubectl get pods` shows `Pending` | S8 Pods Pending |
| Namespace not offloaded | NamespaceOffloading PHASE `NoClusterSelected` | S9 NamespaceOffloading |
| Bridge (extend-proxy) 0/1 Ready | `READY 0/1` on both replicas, or `pool diagnose` shows `NO_HANDSHAKE_AT_POOL` or `STALE_HANDSHAKE_AT_POOL` (UNTESTED) | S10 Bridge not Ready |
| `proxy-test` fails | `000`, `Could not connect`, or a 502 | S11 proxy-test fails |

More than one row matches: fix them in table order. A higher row often causes a lower one (a
hibernated pool makes the virtual node NotReady and the bridge 0/1).

## Step 3: Fix

For the matched section: run its checks, compare with the good and bad results, and propose the
fix. Ask before each change (Rule 1). After the fix, run the triage of Step 1 again and report
what changed. Stop after two failed fixes of the same symptom and go to Step 4.

## Step 4: Escalate to Multicloud

Escalate when `playbook.md` says so, or after two failed fixes.

1. **Support bundle.** Ask, then run (it reads only, and writes one file with mode 600):

   ```bash
   bash <skill-folder>/scripts/support-bundle.sh --pool <pool> --org <org-id> --ns my-apps
   ```

   `<skill-folder>` is the folder of this `SKILL.md`. Without the plugin installed, download the
   script first into `~/multicloud-onboarding/` from
   `https://raw.githubusercontent.com/multicloud/skills/main/plugins/multicloud-troubleshoot/skills/multicloud-troubleshoot/scripts/support-bundle.sh`,
   and read it before you run it.

   It collects IDs, states and log tails only, plus the public IPv4 address the pool sees for your
   cluster (`pool diagnose`, line `Source IP`): pool, pool diagnose, peerings, cloud accounts, connector pods and
   IDs, virtual nodes, NamespaceOffloading phases, workload pods and events, bridge pods, config,
   log and events. It never reads a Secret's content, never runs `mctl peering show` and never
   prints a bundle object. Tell the user to read the file before they send it.
2. **Support access.** Multicloud support logs in to a pool only when an organization owner allows
   it, for a limited time:
   - Console: open the pool, tab **Settings**, card **Support access**, choose a time, click
     **Allow support access**.
   - CLI (owner): `mctl ssh support allow --pool <pool> --for 24h` (default 4h, at most 168h).
     `mctl ssh support list` shows the open consents; `mctl ssh support revoke <id>` ends one at once.
3. **Message.** Tell the user to send the bundle file, the pool name, the organization ID, the
   symptom row and the time the problem started to their Multicloud contact (or
   support@multicloud.io).

## Hand back

```text
MULTICLOUD-RESULT skill=multicloud-troubleshoot status=<done|waiting|blocked> symptom=<S-id> pool=<name> fixed=<yes|no> bundle=<path|none>
```

`status=waiting` when time fixes it (a pool that wakes, a quota request). `status=blocked
who=<network-team|cluster-admin|owner|multicloud-contact>` when a person must act. When the
orchestrator (`multicloud-onboarding`) or `multicloud-extend` sent you, return to the step that
failed after `status=done`.
