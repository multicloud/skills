---
name: multicloud-extend
description: Use when someone wants Multicloud Extend - cloud nodes or a cloud GPU for their own Kubernetes cluster (on-prem, k3s, kubeadm, GKE, EKS) - for example to run an LLM with vLLM on one AWS GPU, burst pods to the cloud, create an Extend pool or peering, install the liqo-consumer chart, apply the peering bundle, offload a namespace, hibernate or wake a pool, or clean up an Extend PoC.
---

# Extend a Kubernetes cluster with Multicloud

The user's cluster gets a virtual node. Pods sent there run on workers in the user's own AWS
account, which Multicloud manages as a **pool**. You check the cluster, create the pool and the
peering, install the connector, and run a first workload. Every command is in `flows/extend.json`
next to this file; the vLLM manifest is `assets/vllm-gpu.yaml`. Use the commands as written there.

## Before you start

You need (ask the user, or take it from the onboarding ledger):
- a **connected, verified AWS cloud account**: its cloud-account ID (`mctl cloud-account list`,
  first column; it is not the 12-digit AWS account ID). None: use skill `multicloud-connect-aws`.
- the **region** of the pool (one of the account's regions).
- the **profile**: `gpu-llm` (one LLM on one GPU) or `cpu-burst`.
- for `gpu-llm`: on-demand G and VT vCPU quota of 4 or more in that region. Unknown or lower: use
  skill `multicloud-quota` first. Never create the GPU pool before the quota is there.
- `kubectl`, `helm` 3.14+, `jq`, and a kubeconfig with cluster-admin rights.

On Windows, run every command inside WSL (`wsl.exe -d <wsl_distro> -- bash -lc '…'`, or a script in the
WSL home folder; see skill `multicloud-workstation`). Keep every file of this skill in a folder in
the WSL home, never under `/mnt/c`.

## Words used in this skill

- **Machines (pool):** the Multicloud machines that run your work in your own AWS account. You pay for
  them by the hour. A paused set costs nothing.
- **Link (peering):** the connection between your cluster and those machines. One link per machine set.
- **Connector:** the Multicloud software installed in your cluster. It makes the link work.
- **Connection file (bundle):** a file from Multicloud that lets your cluster reach the machines. It is
  given once and must stay secret.
- **Multicloud node:** a node in your cluster that stands for the Multicloud machines. Your apps are
  sent there with a namespace setting ("send this namespace").
- **Bridge (proxy):** a small set of pods in your cluster that lets your apps reach an app on the
  Multicloud machines.
- **Your cluster ID:** the ID Multicloud gives your cluster (starts with `c-`).

## Stage order

Every Extend use case runs the proxy stage. The flow runs these stages in this order:

| Profile | Stages, in order |
|---|---|
| `gpu-llm` | `cluster` → `pool-gpu` → `peering` → `run-gpu-llm` → `proxy` → (`cleanup` on request) |
| `cpu-burst` | `cluster` → `pool-cpu` → `peering` → `run-cpu-burst` (the proxy stage's `proxy-target` adds the nginx route target) → `proxy` → (`cleanup` on request) |

## Rules that do not bend

1. **The bundle is read once.** The first read of a READY peering holds the connection file; the
   API deletes it in that read. Run the loop of step `save-bundle` as one script and nothing else.
   Never run `mctl peering show` by hand before the loop ends. Never print, `cat` or copy
   `multicloud-peering.yaml`: it grants access to the pool. Check it with `test -s` only.
2. **The model key stays in the cluster.** Step `model-api-key` makes it with `openssl rand` inside
   the `kubectl create secret` line. Never echo it. Step `first-query` reads it into a shell
   variable in the same command that uses it, then unsets it.
3. **Name the cluster before each change.** Run `kubectl config current-context` and put the
   context in the question: "Install the connector into cluster `<context>`?"
4. **Cost.** Before `create-pool`, say: "An awake pool keeps one worker running. Your cap is
   $<max-cost-per-hour> per hour. `mctl pool hibernate <pool>` stops the cost." Ask, then create.
5. **Ask before each change** (`who_kind` `ask`): pool, peering, helm install, kubectl apply,
   namespace, secret, deploy, deletes. A yes covers one step. Deletes cannot be undone: say so.
6. **The proxy key never leaves Multicloud and the cluster.** Step `proxy-secret` runs
   `mctl extend proxy-key create`: mctl makes the key and saves it as the cluster Secret. The key is
   never printed, never on a command line, never in chat, never in a file. The user needs to be an
   owner and signed in (`mctl auth login`). Never ask for the key, and never make the key in the
   console.

`who_kind` in the flow: `agent` = run it; `ask` = show, ask, then run; `user` = the user does it;
`page` = skip. When a step has `c_agent`, run that instead of `c`.

## Step 1: Check the cluster (stage `cluster`)

Run the steps in order and report each result in one line:
- `kubeconfig`: the user names the kubeconfig path. On Windows, copy a Windows file into WSL first
  (`cp /mnt/c/Users/<u>/Downloads/<file> ~/.kube/config-poc && chmod 600 ~/.kube/config-poc`).
  Use `export KUBECONFIG=…` in every later command. `kubectl auth can-i '*' '*' --all-namespaces`
  must print `yes`. A k3s kubeconfig copied from the server (`/etc/rancher/k3s/k3s.yaml`) points at
  `https://127.0.0.1:6443`: ask the user for the server's address and change the `server:` line in
  the copy (ask first), or run from a machine on the same network. `kubectl get nodes` times out:
  the cluster is not reachable from this computer (VPN, firewall); ask the cluster administrator.
- `version`: Server Version 1.30 or later, and one `validatingadmissionpolicies` line.
- `cidrs`: pod CIDR and service CIDR. k3s: `10.42.0.0/16` and `10.43.0.0/16` unless the server
  flags say otherwise; ask the user to confirm. Not found: ask the cluster administrator.
- `cni`: the network plugin name.
- `pod-proxy`: the API server must reach a pod (`ok`). A 502 (OrbStack Kubernetes) breaks `logs`,
  `exec` and `port-forward` to the pool: stop and ask for another cluster (kind, k3s).
- `free-cpu`: about 115m of free CPU requests on one node; a node at 95% or more is full.
- `egress` (ask: it starts one short pod): docker hub 401, ghcr 401, cloudflare 200 are good.

A failed check: stop and say what the cluster administrator must change. All good: hand back
`status=done stage=cluster` when the orchestrator asked only for this stage (for example while
quota waits).

## Step 2: Create the pool

- `gpu-llm`: stage `pool-gpu`, pool `poc-gpu` (L4 or A10G only, on-demand, 100 GB disk, 16 GB nodes, 2 servers,
  $1.50 per hour). Keep `max_memory_gb: 16`: without it the node ceiling is 4 × `min_memory_gb`
  rounded down to a size tier (8 GB, 7168 MB after overhead), and the vLLM pod (12 Gi) never gets
  a node. The scheduler then logs `Workload requires 12288MB but the node ceiling only allows
  7168MB after overhead`. Fix on a live pool: `mctl pool update <pool> --set max_memory_gb=16`.
- `cpu-burst`: stage `pool-cpu`, pool `burst`.

Put the cloud-account ID and the region into the commands: the flow shows `us-east-1` as an
example; use the region of the quota (GPU) or the region the user chose. Then open the pools page
(`https://multicloud.io/console/pools`) and tell the user they can follow the creation there, and
that they should come back to this chat. Poll `wait-ready` here: run `mctl pool show <pool>` once
a minute until `Status: ready`, at most 20 minutes; then stop and give the output to the user for
their Multicloud contact. Errors: `ACCOUNT_NOT_READY` (409) → verify
the account (skill `multicloud-connect-aws`); a 422 names the bad field.

## Step 3: Connect the cluster (stage `peering`)

0. `check-connector` (agent): if `liqo-consumer` is already installed on this cluster, stop. An
   existing install serves a peering that may still be in use (one consumer ID per install). Show
   the release and its consumer ID, find the peering it serves, and ask the user before any change.
1. `gpu-llm`: step `create-peering`. `cpu-burst`: step `create-peering-cpu`. Note the peering ID
   from `Peering <id> created`, and the whole `Install command:` line.
2. `install-connector` (ask, name the context): the install command with `<POD_CIDR>` and
   `<SERVICE_CIDR>` replaced by the values of Step 1. Change nothing else. The chart must be
   **0.3.1 or later**, with the `reflectionKick.remoteClusterID` line (the pool slug). This applies to
   every customer of chart 0.3.1, with or without the proxy. An older install: `install-connector-upgrade`
   (optional) runs `helm upgrade --reset-then-reuse-values`, then restart the offloaded workloads.
3. `save-bundle`: run the loop with the pool name and the peering ID, as one script. It stops at
   the first response that holds the bundle, at any status other than `PENDING`, and on `mctl`
   exit 3 or 4. After it: `test -s
   multicloud-peering.yaml && echo saved`. Status `SUSPENDED`: the pool hibernates or wakes;
   `mctl pool wake <pool> --wait`, then run the loop again. Empty, or status FAILED: revoke
   (`mctl peering revoke <pool> <peering-id> --yes`, ask first) and create a new peering.
4. `apply-bundle` (ask): the preflight Job name ends with the **consumer cluster ID** (`c-` and 8
   hex characters, from the `clusterID` value of the install command), not the peering ID.
5. `gpu-llm`: `check-gpu` must print `1` (empty in the first two minutes is normal; retry).
   `cpu-burst`: `check-virtual-node` must show `Ready` and the pool slug.

## Step 4: First workload

- `gpu-llm` (stage `run-gpu-llm`): `offload-namespace`, `model-api-key`, `save-manifest` (write
  `assets/vllm-gpu.yaml` unchanged to `vllm-gpu.yaml` in the working folder), `deploy-vllm` (wait
  up to 30 minutes: a new GPU worker and a 15 GB model download), `port-forward` (the `c_agent`
  form runs it in the background), `first-query` (the `c_agent` form). Before the query, check
  that the port-forward lives: `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health`
  must print `200` (on Windows a background process can end with the `wsl.exe` call). Not `200`:
  ask the user to run the `c` form in a second Ubuntu or terminal window and keep it open. Done
  when the model answers. Show the user the answer and the curl form from the page so they can try
  their own prompt.
- `cpu-burst` (stage `run-cpu-burst`): `offload-namespace`, `burst-pod` with the pool slug. Done
  when the log says `hello from the pool`.

## Step 5: Reach the pool from your cluster (stage `proxy`)

The Extend proxy lets a pod or Service in the cluster call a pod on the pool. It runs for **every**
use case, after the first workload (`run-gpu-llm` or `run-cpu-burst`), because its route points at
that workload's namespace (`my-apps`) and Service (`vllm`). That namespace must already be offloaded.
Steps in order:
1. `proxy-target` (ask, `cpu-burst` only): the burst pod exits, so run nginx (a small public web server,
   no GPU, port 80) on the pool in `my-apps` as Service `nginx`. The CPU route points at it.
2. `proxy-manifest` (ask; `proxy-manifest-cpu` for `cpu-burst`): the file comes with this skill
   (`assets/extend-proxy.yaml`, release `multicloud/extend-proxy:0.1.2`), so the user needs nothing from
   anyone else. The agent copies it to `~/multicloud-onboarding/`, fills in the pool, peering ID and the
   route (GPU: Service `vllm` port 8000; CPU: Service `nginx` port 80), checks no placeholder is left,
   dry-runs the apply, shows you the result, and applies only on your yes. The `sed -i.bak` form works with GNU sed and macOS sed. An older copy's `extend-proxy-discovery` objects are deleted only on a yes.
3. `proxy-secret` (ask, owner): `mctl extend proxy-key create --pool <pool> --kube-context <context>`
   after the file of step 2 is applied (it creates the namespace the key goes into). The output says
   the Secret is saved; it never shows the key. Ask first; a second run needs `--replace` and a yes.
4. `proxy-check` (agent): both replicas show `READY 1/1`. Then hand back `proxy=ready`.
5. `proxy-restart` (optional, ask): only for offloaded workloads that already run. None on a first run.
6. `proxy-test` (agent): run it only after the first workload is up on the pool (`deploy-vllm` in
   `run-gpu-llm`, or `proxy-target` for `cpu-burst`). Any HTTP status means the path works (vLLM
   answers 401 without its key).

Notes for the user:
- `HOST_FIREWALL_OFF` in the proxy log: ask Multicloud to turn on the pool network. The proxy retries.
- The replicas show NotReady while the pool sleeps. Do not act; they become Ready when the pool wakes.
- An offloaded pod not restarted since the chart change has no address. Restart it (`proxy-restart`).

If the user declines the proxy: say that a pod in the cluster calling a pod on the pool will not
work, and record `proxy=skipped`. If the check fails and cannot be fixed, record `proxy=blocked`
and ask the Multicloud contact.

## Pause, resume, clean up

- Stop for the day: `mctl pool hibernate <pool>` (ask). Resume: `mctl pool wake <pool> --wait`. A
  peering cannot be created on a hibernated pool (409 `POOL_HIBERNATED`).
- Clean up only when the user asks: stage `cleanup`, in the order of the flow. The proxy goes first
  (`kubectl delete namespace multicloud-extend-proxy`): when it stops, it removes its registration with
  its key. Then the user revokes the `extend-proxy` key in the console (for `cpu-burst`, skip
  the vLLM lines and use pool `burst`). Put the real region, AWS profile and connection folder
  (from the onboarding ledger or skill `multicloud-connect-aws`) into the `<…>` placeholders. Ask once for the whole list and say that the pool delete
  cannot be undone. Stop the background port-forward first:
  `kill "$(cat ~/multicloud-onboarding/port-forward.pid)"`. Then `check-nothing-left` (its `aws`
  command needs an AWS sign-in to the account: put `AWS_PROFILE=<profile>` before it; for a new
  account without a sign-in there, skip it, because closing the account removes everything in it).
- The AWS connection stays unless the user asks to remove it (steps `aws-connection-new` for a new
  account Multicloud's Terraform created, `aws-connection-existing` for an account the user has; skill
  `multicloud-connect-aws`, section Disconnect). If the onboarding used an IAM user access key
  (path B), remind the user to delete it.

## Hand back

```text
MULTICLOUD-RESULT skill=multicloud-extend status=<done|waiting|blocked|failed> profile=<gpu-llm|cpu-burst> pool=<name> peering_id=<id> consumer_cluster_id=<c-…> first_run=<yes|no> proxy=<ready|skipped|blocked>
```

`status=blocked who=cluster-admin` for a failed cluster check, `who=multicloud-contact` for a pool
that does not get ready, a preflight Job that fails twice, or a proxy that stays not ready.
`proxy=` is always set: `ready` after `proxy-check`, `skipped` if the user declined, `blocked` if the
check fails.
