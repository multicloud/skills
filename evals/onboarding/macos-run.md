# macOS live run of multicloud-onboarding (door Extend, gpu-llm)

Date: 2026-11-15. Machine: Apple silicon Mac, macOS (Darwin 25.6.0). Branch `claude/multicloud-onboarding`.
Org `multicloud-testing-c33d5635ed`. AWS account dev2 (431412299678), region us-east-1.
Consumer cluster: OrbStack Kubernetes v1.36.5+orb1 (single node, IPv4 pod and service CIDRs).
Approved spend cap: $1 per hour (the skill default is $1.50), 3 hours.

## Coverage

| Item | Result | Evidence |
|---|---|---|
| OS detection | PASS | `uname -s` → `Darwin`, `run_prefix=none` |
| Ledger folder 700, file 600 | PASS after fix | `stat -f %Lp` → 700 / 600; a `jq … > tmp && mv` update made the file 644 (bug 1) |
| Tool installs | NOT COVERED | all tools were already installed on this Mac |
| `mctl` upgrade | PASS | `uv tool upgrade multicloud-cli` → 0.9.1 to 0.10.1 |
| Helm 4 against "3.14 or later" | see Extend stage | brew ships Helm 4.2.3 |
| Sign-in | PASS | `mctl auth status` → `The sign-in works.`, 3 organizations, `--org` used |
| connect-aws create | PASS | `Cloud account 19 created`, module `multicloud/multicloud/aws` 2.0.0 |
| connect-aws plan and apply | PASS | `Plan: 4 to add, 0 to change, 0 to destroy`; `Apply complete! Resources: 4 added` |
| connect-aws verify | PASS after owner step | `ACCOUNT_NOT_DEDICATED: created before connect` (bug 2); owner typed the ID in `accept-shared-account 19` → `Ready: ... connected as a shared account`, 4 × `quota OK` |
| quota | PASS | `quota-plan 19 --region us-east-1` → `ondemand-g (L-DB2E81BA): limit 4`, `quota=enough` |
| Extend cluster stage | PASS | can-i `yes`; one `validatingadmissionpolicies`; pod `192.168.194.0/25`, service `192.168.194.128/25`; egress 401/401/200 with `-i` (bug 3) |
| Fractional GPU guard | PASS (not a bug) | cheapest on-demand L4 is `g6f.large` (1/8 GPU); `ServerResourcesConstraint.java:199` rejects fraction < 1 unless `allowFractional` is true |
| Pool create | PASS | `Pool 1038 (poc-gpu) created. Status: PROVISIONING` |
| GPU node for vLLM (12 Gi) | PASS after fix | scheduler: `Workload requires 12288MB but the node ceiling only allows 7168MB after overhead` (196 times); `mctl pool update poc-gpu --set max_memory_gb=16` → GPU node up (bug 5) |
| Port-forward on OrbStack | FAIL (cluster, not skill) | `proxy error from 127.0.0.1:26443 while dialing 192.168.194.14:10250, code 502`; the apiserver gives 502 even to the CoreDNS pod IP (bug 7) |
| Second consumer: kind (Kubernetes in Docker) | PASS | `apiserver->pod: OK`; `deployment.apps/vllm condition met`; `health=200`; first query → `Hello! How can I assist you today?` |
| Cleanup | PASS after fix | peerings 25, 26 `REVOKED`; pool 1038 deleted; account 19 revoked, `No leftovers`; tenant namespace deleted with no hang after the finalizer patch (bug 6) |

## Skill bugs found

1. Orchestrator: no rule keeps the ledger at mode 600 on update. A rewrite through a temp file
   gets the default umask (644).
2. connect-aws: the result table has no row for `ACCOUNT_NOT_DEDICATED` and the owner step
   `mctl cloud-account accept-shared-account <n>` (interactive, the owner types the AWS account ID).
   Every customer with an existing AWS account meets it.
3. extend `egress`: `kubectl run … -it` prints nothing from an agent shell (no TTY). Use `-i`.
4. extend cluster `cidrs`: covers kubeadm and k3s only. `kubectl get servicecidrs` (Kubernetes 1.33+)
   and the node `spec.podCIDRs` give both CIDRs on any cluster.

5. extend `pool`: a Kamaji pool caps each node at 4 × `min_memory_gb`, rounded down to the
   4/8/16/32/64 GB tiers, minus 1024 MB. With the default, vLLM (12 Gi) never fits and the pool
   buys no GPU node. The flow now sets `max_memory_gb` 16 at create (commit 0037f6a).
6. extend `cleanup`: deleting the bundle removes the Liqo bridge, so Liqo cannot clear the
   finalizers on `NamespaceMap` and `ResourceSlice`, and the tenant namespace hangs. The flow now
   deletes the bundle before the revoke and clears those finalizers (commit 42d3ddb).
7. extend cluster: no check that the API server can dial a pod IP. On OrbStack it cannot (502),
   so `port-forward`, `logs` and `exec` to the pool fail. The new `pod-proxy` step calls
   `kubectl get --raw .../pods/<coredns>:8080/proxy/health` and stops on anything but `ok`
   (commit 42d3ddb).

## Not skill bugs

- `mctl cloud-account quota-plan` prints a raw Python dict on the `Request budget:` line.
- `mctl peering create` prints `Next: mctl peering show …`. A person who runs it uses up the
  fetch-once bundle, and the skill's bundle loop then fails.
- Platform latency: on the kind run, GPU server 5528 (g6.xlarge) stayed `STARTING` for 31 minutes
  before EC2 launched it (row 21:02 UTC, instance launch 21:33:43 UTC). Needs a scheduler check.
- OrbStack Kubernetes cannot be a consumer cluster for Extend (bug 7). Use kind, k3d or a cloud cluster.
