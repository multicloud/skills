# Verified: Extend GPU and CPU routes

This file lists what has been proven working in a live run of the `multicloud-extend` skill. Other agents and reviewers: check it before you assume a step works. Update it when a step is verified with evidence. Do not add anything without a test result behind it.

Last updated: 2026-11-18.

## Verified

| Item | Evidence | Date |
|---|---|---|
| AWS account connected to Multicloud (cloud account created by `multicloud-connect-aws`) | Skill result line | 2026-11-17 |
| Quota in us-east-1 for on-demand and spot G and VT instances is enough | `mctl cloud-account verify` (live) | 2026-11-17 |
| CPU route end to end: laptop, kubectl port-forward, cluster, Extend proxy, pool. Response `hello from the pool`, HTTP 200 | Live test, confirmed by the operator | 2026-11-17 |
| The proxy key is created by `mctl extend proxy-key create` and stored in the cluster namespace `multicloud-extend-proxy`. The customer never copies it | Live run | 2026-11-17 |
| Cluster has room for the connector: CPU requests on the node at 28% | `kubectl describe node` | 2026-11-18 |
| GPU pool created and ready: 1 node, cost cap $1.50/h, accelerators L4 and A10G | `mctl pool show` | 2026-11-18 |
| Connector for the GPU pool installed (`liqo-consumer` chart 0.4.0); preflight job completes | `helm`, `kubectl wait` | 2026-11-18 |
| GPU virtual node is Ready and reports `nvidia.com/gpu: 1` | `kubectl get node -l liqo.io/type=virtual-node` | 2026-11-18 |
| vLLM (Qwen2.5-7B-Instruct) starts on the GPU pool and answers in the pod: no key gives 401, the key gives a model answer. First start took about 25 minutes, mostly the model download | In-pod request test | 2026-11-18 |
| GPU route end to end: laptop, kubectl port-forward, cluster, Extend proxy (route to `vllm`, port 8000), pool, vLLM. No key gives 401, the key gives a model answer | Live tunnel test | 2026-11-18 |
| The GPU proxy key is created with `mctl extend proxy-key create --pool <gpu pool> --replace` and written to the cluster secret. The proxy registers (status PENDING until activated) | `mctl` output, proxy log | 2026-11-18 |

## Not yet verified

- The GPU proxy reaches ACTIVE status (it was PENDING at the last check).
- The CPU route on a second pool: the earlier pool's connector was replaced, so it needs a new peering first.
- The old proxy key used before `--replace` must be revoked in the console. That step is manual.

## Known issues from this track

- The org limit is 3 active pools, and hibernated pools count toward it. Ask Multicloud to raise the limit if needed.
- Replacing the cluster's connector removes the old pool's virtual node and link. Do this only with the owner's approval.
- The pool must have host firewall enforced before the proxy registers. Otherwise the proxy log shows `HOST_FIREWALL_OFF` (platform issue #1559).
- A hung `kubectl drain` can leave NodeShutdown pods behind. Clean them up after a resize to zero.
- `helm uninstall` of the connector can fail on a Liqo pre-delete hook when the controller is already gone. Use `--no-hooks`, then remove the leftover hook jobs.
