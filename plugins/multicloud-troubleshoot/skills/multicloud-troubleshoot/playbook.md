# Playbook: symptom, checks, fix

Each section has the same parts: **Check** (read-only commands), **Good** and **Bad** (what the
output looks like), **Fix** (what the customer can change; ask first), **Escalate** (when to go to
Step 4 of `SKILL.md`).

Placeholders: `<pool>` pool name, `<org-id>` organization ID, `<slug>` the pool slug (the
`multicloud.io/pool` label of the virtual node and the `remoteClusterID` of the connector),
`<ns>` the offloaded namespace (default `my-apps`), `<id>` the cloud-account ID.

Several organizations: add `--org <org-id>` to every `mctl` line below (Rule 4).

A line marked `# UNTESTED` was not run by the skill authors (see "Test record" at the end).

---

## S1 Sign-in and organization

**Check**

```bash
mctl auth status
mctl pool list
```

**Good:** `pool list` prints the table `ID NAME TYPE STATUS NODES COST/H`.

**Bad, and the fix:**

| Output | Meaning | Fix |
|---|---|---|
| `Error: Your session ended. Run: mctl auth login` | The sign-in expired. | The user runs `mctl auth login` (browser). |
| `You belong to several organizations (a, b). Name one with --org or MULTICLOUD_ORG.` (UNTESTED: text from the mctl source) | No organization chosen. | Add `--org <org-id>` to every command, or `export MULTICLOUD_ORG=<org-id>` for this shell. |
| `pool list` or `cloud-account list` prints only the header, or a pool you know gives "not found" (exit 4) | mctl used another organization: a saved default, or the wrong `--org`. It gives no error. | `mctl auth status` lists your organizations. Run again with `--org <org-id>` for the organization that owns the pool. |
| `Error: You are not a member of '<org>'. Your organizations: …` (exit 3) | Wrong organization ID. | Use one ID from the list. |

mctl exit codes: 0 ok, 1 error, 2 usage, 3 not signed in or no access, 4 not found, 5 pending or
timeout, 6 deleted.

**Escalate:** never for this symptom; an organization owner adds users in the console.

---

## S2 Cloud account not verified

**Check**

```bash
mctl cloud-account list
mctl cloud-account show <id>
```

**Good:** STATUS `verified`; `show` prints `Status: verified (Ready)` and a recent `Last check`.

**Bad:**
- `pending`: the connection is not finished.
- `degraded`: the last check failed; `show` prints a `Reason`.
- `revoked`: the account is disconnected. Use another account or connect again.
- Pool create fails with `ACCOUNT_NOT_READY` (409) or `CLOUD_NOT_CONNECTED`.

**Fix (ask: `verify` can turn on AWS opt-in regions):**

```bash
mctl cloud-account verify <id>        # UNTESTED: exit 0 verified, 5 still pending, 1 failed
```

- Exit 5: an IAM change still spreads. Run it again in two minutes, or add `--wait`.
- Exit 1 with `Missing permissions:`: the IAM role in your AWS account lacks them. Re-apply the
  connection with skill `multicloud-connect-aws` (it owns the Terraform), then verify again.
- Check the role from your side (the `Role:` line of `show`):

  ```bash
  aws sts get-caller-identity                     # UNTESTED
  aws iam get-role --role-name <role-name> --query 'Role.Arn'   # UNTESTED
  ```

**Escalate:** `verify` fails and the role and its trust policy are as Terraform made them.

---

## S3 Quota too low

**Check** (files nothing):

```bash
mctl cloud-account quota-plan <id> --region <region>
```

**Good:** for a GPU pool, `ondemand-g (L-DB2E81BA): limit 4` or more (one L4 or A10G worker needs
4 vCPU). For spot GPU workers, `spot-g (L-3819A6DF)` 4 or more. CPU pools: `ondemand-standard` and
`spot-standard` above the vCPU of `max-servers` workers.

**Bad:** `limit 0` (new accounts often start at 0), an `OPEN request` not yet approved, or
`DENIED <date> … wait until <date>`.

From your own AWS account:

```bash
aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA \
  --region <region> --query 'Quota.Value'                    # UNTESTED
aws service-quotas list-requested-service-quota-change-history --service-code ec2 \
  --region <region> --query 'RequestedQuotas[].[QuotaCode,DesiredValue,Status]' --output text   # UNTESTED
```

**Fix:** use skill `multicloud-quota`. It plans and files only what the user approves. An approval
can take hours or days: `status=waiting`.

**Escalate:** no; quota is between the customer and AWS. A denial: ask AWS Support.

---

## S4 Pool slow to wake, or stuck waking

**Check**

```bash
mctl pool show <pool>
mctl pool show <pool> --json | jq '{status, status_message, node_count, hibernated_reason}'
```

**Good:** `Status: ready`. A wake normally takes **8.5 to 11 minutes**; plan for up to 20.

**Bad:**

| Output | Meaning | Fix |
|---|---|---|
| `Status: hibernated` | The pool sleeps. Everything else (virtual node, bridge) waits. | Ask, then `mctl pool wake <pool> --wait --timeout 20m` (exit 0 ready, 5 timeout). |
| `Hibernated reason: PAYMENT_SUSPENDED`, or wake fails with 402 (UNTESTED: from the API source) | Billing stopped the pool. | An owner checks `mctl billing` and the console billing page. |
| `waking` or `provisioning` with the same message for less than 20 minutes | Normal. A spot reclaim on Multicloud's side can make one wake slower. | Wait. Check again once a minute. |
| `waking` or `provisioning` with the same message for **more than 20 minutes**, or the message `STATE_STALE` (UNTESTED: from the API source) | The wake is stuck on Multicloud's side. | Escalate. |
| `Status: disabled` | The pool is turned off. | Escalate. |

**Escalate:** after 20 minutes in `waking` or `provisioning`. Put in the message: the pool name,
the `status_message`, and the time you started the wake. The cause is almost always on Multicloud's
side; you cannot fix it from your cluster.

---

## S5 Pool has no worker

A pool starts a worker only when a pod waits on the virtual node. A new worker takes about 5.5
minutes. An idle worker stops after `idle_reap_minutes` (10 by default). `Nodes: 0` with no
waiting pod is normal.

**Check**

```bash
mctl pool show <pool>                  # Nodes, Cost per hour: X of Y allowed
mctl pool cluster <pool>               # the nodes of the pool
kubectl -n <ns> get pods -o wide       # a pod Pending for the virtual node?
```

**Bad, and the fix:**

| Output | Meaning | Fix (ask first) |
|---|---|---|
| `Cost per hour: X of Y allowed` with X near Y, or STATUS `at_cost_cap` in `pool list` | The cost cap blocks a new worker. | `mctl pool update <pool> --max-cost-per-hour <n>` (UNTESTED: only its help text was read). Or more workers: `--max-servers <n>`. |
| No pod waits | Nothing to run. | Start the workload. |
| A GPU pod waits, no worker after 10 minutes | GPU quota or GPU settings. | S3. The pool needs `accelerator_names` and the peering `--gpu 1`. |
| The pod waits with a scheduling error | The pod never reaches the pool. | S8. |

Workers launched in your AWS account (pool workers carry the tag `multicloud-cluster-id`):

```bash
aws ec2 describe-instances --region <region> \
  --filters Name=instance-state-name,Values=pending,running Name=tag-key,Values=multicloud-cluster-id \
  --query 'Reservations[].Instances[].[InstanceId,InstanceType,InstanceLifecycle,LaunchTime]' \
  --output text                                              # UNTESTED
```

**Escalate:** `Nodes: 0`, a pod waits, the cost is below the cap, quota is enough, and 20 minutes
have passed.

---

## S6 Peering not READY, or the preflight Job fails

**Check** (never `mctl peering show` here: Rule 3)

```bash
mctl peering list <pool>
kubectl -n liqo get jobs | grep multicloud-peering-preflight
helm get values liqo-consumer -n liqo -o json \
  | jq -r '.liqo.discovery.config.clusterID, .reflectionKick.remoteClusterID'
```

**Good:** your peering is `READY`; the Job `multicloud-peering-preflight-<slug>-<consumer-id>` is
`Complete 1/1`; its log says `pre-flight OK: clusterID <id>`. The consumer ID (`c-` and 8 hex
characters) in the CONSUMER column equals the `clusterID` of the connector.

**Bad, and the fix:**

| STATUS and MESSAGE | Fix (ask first) |
|---|---|
| `SUSPENDED`, "The pool is hibernated…" | S4: wake the pool. The peering works again by itself. |
| `PENDING` | Wait. It becomes `FAILED` after 20 minutes. |
| `FAILED`, or the bundle file is empty or lost | Revoke and create a new peering (skill `multicloud-extend`, stage `peering`). Revoking cannot be undone. |
| `REVOKED` | Create a new peering. |
| CONSUMER differs from the connector `clusterID` | The bundle was made for another install. Create a new peering for this connector. |

The preflight Job log:

```bash
kubectl -n liqo logs job/multicloud-peering-preflight-<slug>-<consumer-id>
```

- `Multicloud peering pre-flight FAILED: installed clusterID=<a>, bundle minted for <b>` (or
  `<liqo not installed>`): the connector is missing or has another ID. Re-run the `Install
  command` of the peering (skill `multicloud-extend`, step `install-connector`), then apply the
  bundle again.
- The Job never starts: `kubectl -n liqo get pods` must show the connector pods `Running` first.

A connector that was uninstalled and installed again cannot reuse an old bundle. Delete the old
bundle objects first (`kubectl delete -f multicloud-peering.yaml`, ask first), then revoke, then
create a new peering. Revoking first leaves Liqo objects that do not delete. The file is gone:
do not guess which objects to delete; escalate (Step 4) with the peering ID.

**Escalate:** `FAILED` with a message that names Multicloud (for example `INTERNAL`), `PENDING`
for more than 20 minutes on a ready pool, or the preflight Job fails twice with the right
`clusterID`.

---

## S7 Virtual node missing, NotReady or tainted

**Check**

```bash
kubectl -n liqo get pods
kubectl get nodes -l liqo.io/type=virtual-node -L multicloud.io/pool
S=<slug>
kubectl get node "$S" -o jsonpath='{range .status.conditions[*]}{.type}={.status} {.reason}{"\n"}{end}{range .spec.taints[*]}{.key}={.value}:{.effect}{"\n"}{end}'
kubectl -n "liqo-tenant-$S" get pods                              # UNTESTED: vk-<slug>-… 1/1 Running
kubectl -n "liqo-tenant-$S" logs "deploy/vk-$S" --tail=100        # UNTESTED
```

**Good:** one node named `<slug>`, `Ready`, POOL column `<slug>`. Taints: only
`multicloud.io/pool=<slug>:NoSchedule` and Liqo's own `virtual-node.liqo.io/not-allowed` (any
value and effect).

**Bad, and the fix:**

| Output | Meaning | Fix |
|---|---|---|
| No virtual node | The bundle is not applied, or the peering is not READY. | S6. |
| `NotReady` while the pool is `hibernated` or `waking` | Normal. | S4: wake, then wait about 5 minutes. |
| `NotReady` or `Unknown` with the pool `ready` | The connector cannot reach the pool. | Check `kubectl -n liqo get pods` (all `Running`). Outbound HTTPS (443) from the cluster must be open. |
| Taint `node.kubernetes.io/network-unavailable`, condition `NetworkUnavailable=True` | A GKE cluster with routes-based networking. | Use a VPC-native cluster. Do not patch the condition. |
| The node is gone; events say it `does not exist in the cloud provider` | Old connector chart. | Ask, then delete the vk pod in `liqo-tenant-<slug>` (it comes back with the node). Upgrade the connector. Never delete the VirtualNode object. |
| The node turns NotReady every one or two minutes; the vk pod has events `Preempted` | Your cluster is full. | Free about 115m CPU on a node, or add a node. |

**Escalate:** the pool and the peering are `READY`, the connector pods run, outbound 443 is open,
and the node stays NotReady for 10 minutes.

---

## S8 Pods Pending on the virtual node

**Check**

```bash
kubectl -n <ns> get pods -o wide
kubectl -n <ns> get events --field-selector reason=FailedScheduling \
  -o custom-columns=OBJ:.involvedObject.name,MSG:.message
```

**Bad, and the fix:**

| Event text | Fix (ask first) |
|---|---|
| `had untolerated taint {multicloud.io/pool: <slug>}` | Add both to the pod: toleration `multicloud.io/pool=<slug>:NoSchedule` and nodeSelector `multicloud.io/pool: <slug>`. |
| `didn't match Pod's node affinity/selector` only | The nodeSelector names another slug. A pool created again has a new slug: change the manifest. |
| `Too many pods`, `Insufficient cpu` or `Insufficient memory` on the virtual node | The request is larger than the peering grant. Lower the request, or create a peering with a larger grant. |
| `quota` in the message | The pod asks for a resource the grant lacks (a GPU without `--gpu 1`), or a container has no `requests`. |
| No event, pod Pending right after a wake | Wait about 30 seconds. |
| The virtual node is NotReady | S7. |

`OffloadingBackOff` events on DaemonSet pods are normal and do not block anything.

**Escalate:** the event says nothing above, and the virtual node is Ready.

---

## S9 NamespaceOffloading `NoClusterSelected`

**Check**

```bash
kubectl get namespaceoffloadings.offloading.liqo.io -A \
  -o custom-columns=NS:.metadata.namespace,PHASE:.status.offloadingPhase
kubectl -n <ns> get namespaceoffloadings.offloading.liqo.io offloading \
  -o jsonpath='{.spec.clusterSelector.nodeSelectorTerms}'; echo
kubectl get nodes -l liqo.io/type=virtual-node
kubectl -n liqo logs deploy/liqo-controller-manager --tail=300 \
  | grep -E 'Required value|No NamespaceMaps' | tail -n 3
```

**Good:** PHASE `Ready`.

`NoClusterSelected` has two causes. Tell them apart with the second and third commands:

| Selector (2nd command) | Virtual node (3rd) | Controller log | Cause | Fix (ask first) |
|---|---|---|---|---|
| empty | any | `spec.clusterSelector.nodeSelectorTerms: Required value` | The object has no `clusterSelector`. | Apply the NamespaceOffloading of skill `multicloud-extend` (step `offload-namespace`), with `matchExpressions: [{key: liqo.io/type, operator: In, values: [virtual-node]}]`. |
| set | none | `No NamespaceMaps are present` | No virtual node yet. | S6 and S7. The phase changes by itself when the node exists. |

`helm uninstall liqo-consumer` deletes every NamespaceOffloading. After a new install, apply it
again.

**Escalate:** the selector is set, the virtual node is Ready, and the phase stays
`NoClusterSelected` for 5 minutes.

---

## S10 Bridge (extend-proxy) 0/1 Ready

A bridge replica is Ready only when two things hold: its registration with Multicloud is active,
and at least one WireGuard handshake with the pool is fresh (less than 3 minutes old). The bridge
sends WireGuard on **UDP 51820** from a random source port to IPv4 addresses of the pool.

**Check**

```bash
mctl pool show <pool>                                   # must be ready
mctl pool show <pool> --json | jq '.managed.host_firewall'   # must be true
kubectl -n multicloud-extend-proxy get pods
kubectl -n multicloud-extend-proxy get events --sort-by=.lastTimestamp \
  -o custom-columns=REASON:.reason,MSG:.message | tail -n 5
kubectl -n multicloud-extend-proxy get secret extend-proxy-api-key -o name
kubectl -n multicloud-extend-proxy get configmap extend-proxy-config -o jsonpath='{.data.config\.yaml}'
kubectl -n multicloud-extend-proxy logs deploy/extend-proxy --tail=40
```

**Good:** both replicas `1/1 Running`; the log has a line `registered` with `proxy_id`; `pool` and
`peering_id` in the ConfigMap match `mctl peering list <pool>` (a `READY` peering).

Read the first bad result, top to bottom:

| Output | Cause | Fix (ask first) |
|---|---|---|
| Pool `hibernated` or `waking` | The pool sleeps. | Normal. Do not act on the bridge. S4: wake the pool; the replicas become Ready by themselves. |
| `CreateContainerConfigError`, event `secret "extend-proxy-api-key" not found` | The bridge key was never saved. | An owner runs `mctl extend proxy-key create --pool <pool> --kube-context <context>` (skill `multicloud-extend`, step `proxy-secret`). |
| `registration failed; backing off` with `HTTP 401` `Invalid API key` | The key is revoked or wrong. | An owner runs the same command with `--replace`. |
| `registration failed; backing off` with `HOST_FIREWALL_OFF`, or `host_firewall` is `false` | The pool network is not on. | Escalate: Multicloud turns it on. The bridge retries by itself. |
| `registration failed; backing off` with `POOL_HIBERNATED` or `WG_MESH_NOT_ON` | The pool is not ready yet. | Wait for S4. |
| `registration failed; backing off` with `WG_PROXY_KEY_IN_USE` | The key is registered on another peering. | Use one key per peering: make a new key with `--replace`. |
| `registration refused for good; retry in 1 h` with `PEERING_REVOKED` | The ConfigMap names a revoked peering. | Put the `READY` peering ID into `peering_id` (skill `multicloud-extend`, step `proxy-manifest`), apply, then `kubectl -n multicloud-extend-proxy rollout restart deploy/extend-proxy`. |
| `registration refused for good` with `POOL_DISABLED` | The pool is turned off. | Escalate. |
| `poll failed; keeping the current peers` | The bridge cannot reach the Multicloud API. | Outbound HTTPS 443 from the cluster to `api.multicloud.io`. |
| `cannot create the WireGuard device` or `peer sync failed` | A node or kernel problem in your cluster. | Escalate with the log. |
| **A `registered` line, the pool is ready, `host_firewall` is true, no error after it, and both replicas stay 0/1 for more than 3 minutes** | **Outbound UDP 51820 is blocked.** The log does not name this cause. | See below. |

**Outbound UDP 51820 blocked.** The test must end on a listener outside the customer's network,
because a UDP send exits 0 even when a firewall drops the packet:

1. The user starts a listener on a host with a public IPv4 address: `nc -u -l 51820`.
2. Ask, then send one packet from inside the cluster:

   ```bash
   kubectl run udp-check --rm -i --restart=Never --image=busybox:1.36 -- sh -c \
     'echo multicloud-udp-test | nc -u -w 2 <outside-ip> 51820'
   ```

3. The text `multicloud-udp-test` must arrive at the listener. `nc` printing nothing and exiting
   0 proves nothing.

No such host: ask the network team for a written answer. The rule they must allow: outbound UDP
51820 from every cluster node (or the NAT gateway) to any IPv4 address, from any source port, with
return traffic. Nothing inbound. Then tell Multicloud the time of the test, so they can confirm on
the pool side that handshakes arrive. Never invent a Multicloud test endpoint.

`kubectl rollout restart` while no replica is Ready leaves the old pods running beside the new
one. That is normal: the rollout waits for a Ready pod.

**Escalate:** UDP 51820 is proven open (the test text arrived), the pool and the peering are
ready, `host_firewall` is true, and the replicas stay 0/1. Put the bridge log in the bundle.

---

## S11 `proxy-test` fails

**Check** (ask: it starts one short pod in `default`; the test of skill `multicloud-extend`, step
`proxy-test`; route `vllm-pool`, port 8000):

```bash
kubectl -n default run proxy-test --rm -i --restart=Never --image=curlimages/curl:8.10.1 -- \
  curl -sS -m 10 -o /dev/null -w '%{http_code}\n' http://vllm-pool.multicloud-extend-proxy.svc:8000/
kubectl -n <ns> get pods -o wide
```

**Good:** any HTTP status (`200`; vLLM answers `401` without its key).

**Bad, and the fix:**

| Output | Cause | Fix (ask first) |
|---|---|---|
| `000` and `Could not connect to server` | No bridge replica is Ready. | S10. |
| The workload pod has no IP in `get pods -o wide` | The pod ran before the connector chart 0.3.1 and was not restarted. | `kubectl -n <ns> rollout restart deployment/<name>`. A bare pod: delete it and apply it again. |
| `502`, or the bridge log says `forward: no backend` | No pod of the target Service runs on the pool, or it has no IP. | Check the route in the ConfigMap (`namespace`, `service`, `port`) and that the pod runs on the virtual node. |
| The bridge log says `connection refused` to an `fd00:…` address | The server listens only on IPv4. Pool pods have only an IPv6 address. | nginx: `listen [::]:80;`. vLLM: `--host ::`. Then restart the pod. |
| The bridge log says `node filter removed every pool pod of the Service` | The pool slug in the bridge config differs from the virtual node name. | Put the slug from `kubectl get nodes -l liqo.io/type=virtual-node` into the ConfigMap. |

The EndpointSlice of a Service that selects pool pods stays empty. That is normal: the bridge
finds the pods itself.

**Escalate:** the bridge is Ready, the pod runs on the virtual node with an IPv6 address, listens
on `::`, and the test still fails.

---

## Test record

Run on 2026-11-18 by the skill authors.

**Tested on a local kind cluster** (Kubernetes 1.33.1, chart `liqo-consumer` 0.3.1, bridge
`multicloud/extend-proxy:0.1.2`, a node object with the virtual-node labels and taints, no real
pool):
- S6: `kubectl -n liqo get jobs | grep …`, the `helm get values … | jq` line.
- S7: `kubectl -n liqo get pods`, the virtual-node list, the conditions-and-taints jsonpath.
- S8: both commands; the event texts `untolerated taint {multicloud.io/pool: <slug>}`, `didn't
  match Pod's node affinity/selector` and `Too many pods` are real output.
- S9: all four commands; both causes reproduced (`Required value` without a selector,
  `No NamespaceMaps are present` with a selector and no virtual node).
- S10: all `kubectl` lines; `CreateContainerConfigError` with `secret "extend-proxy-api-key" not
  found`; `registration failed; backing off` with `HTTP 401` `Invalid API key` (a made-up key);
  the rollout behaviour; `nc -u` exits 0 when the packet is dropped (sent to 192.0.2.1).
- S11: the `proxy-test` command; `000` and `Could not connect to server` with no Ready replica.
- Step 4: `scripts/support-bundle.sh`; its output was searched for keys, tokens and long base64
  strings, and none were found.

**Tested with `mctl` 0.12.0** (read-only, on a test organization): `auth status`, `pool list`
(with and without `--org`, with a wrong `--org`, and with an `--org` that owns no pool: an empty table, exit 0), `pool show` and `--json`, `pool cluster`,
`peering list` (`SUSPENDED`, `REVOKED`), `cloud-account list`, `cloud-account show`, `quota-plan`,
`ssh support list`, `overview`; the error `Your session ended`. `mctl` prints pool states in lower
case (`hibernated`).

**Not tested (marked `UNTESTED` or below):** every `aws` command; `mctl cloud-account verify`;
`mctl pool update`; `mctl pool wake` (it changes state); `mctl ssh support allow` and `revoke`;
`mctl extend proxy-key create`; the text `You belong to several organizations…` (taken from the
mctl source); the `liqo-tenant-<slug>` commands, the preflight Job log lines, the bridge log lines
`registered`, `HOST_FIREWALL_OFF`, `WG_*`, `PEERING_REVOKED`, `poll failed`, `forward: no
backend`, `connection refused` and `node filter …` (taken from the bridge and scheduler source);
any check that needs a live pool.
