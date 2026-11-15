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

## Skill bugs found

1. Orchestrator: no rule keeps the ledger at mode 600 on update. A rewrite through a temp file
   gets the default umask (644).
2. connect-aws: the result table has no row for `ACCOUNT_NOT_DEDICATED` and the owner step
   `mctl cloud-account accept-shared-account <n>` (interactive, the owner types the AWS account ID).
   Every customer with an existing AWS account meets it.
3. extend `egress`: `kubectl run … -it` prints nothing from an agent shell (no TTY). Use `-i`.
4. extend cluster `cidrs`: covers kubeadm and k3s only. `kubectl get servicecidrs` (Kubernetes 1.33+)
   and the node `spec.podCIDRs` give both CIDRs on any cluster.

## Not skill bugs (follow-ups for mctl)

- `mctl cloud-account quota-plan` prints a raw Python dict on the `Request budget:` line.
