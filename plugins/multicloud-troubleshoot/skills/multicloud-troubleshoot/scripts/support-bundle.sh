#!/usr/bin/env bash
# Collect a Multicloud Extend support bundle: IDs, states and log tails only.
#
#   support-bundle.sh --pool <pool> [--org <org-id>] [--ns <offloaded-namespace>] [--out <file>]
#
# Read-only. It runs only the commands listed below (an allow-list), on the current
# kubectl context and as the signed-in mctl user. It never reads the content of a Secret (it checks only that the
# bridge key Secret exists), never prints a
# bundle-created object as YAML, never runs `mctl peering show` (the first read of a READY
# peering returns the bundle once) and never runs `helm get values --all`.
# Check the file before you send it. Every line in it came from your own cluster or account.
set -uo pipefail

POOL="" ORG="" NS="my-apps" OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pool) POOL="$2"; shift 2 ;;
    --org)  ORG="$2"; shift 2 ;;
    --ns)   NS="$2"; shift 2 ;;
    --out)  OUT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$POOL" ] || { echo "usage: $0 --pool <pool> [--org <org-id>] [--ns <namespace>] [--out <file>]" >&2; exit 2; }
OUT="${OUT:-$HOME/multicloud-onboarding/support-bundle-$(date -u +%Y%m%dT%H%M%SZ).txt}"
umask 077
mkdir -p "$(dirname "$OUT")"

if [ -z "$ORG" ]; then
  orgs="$(mctl auth status 2>/dev/null | sed -n 's/^Organizations: //p')"
  [ -n "$orgs" ] || { echo "mctl lists no organization (not signed in?). Run mctl auth login, or pass --org <org-id>." >&2; exit 2; }
  case "$orgs" in
    *,*) echo "You belong to several organizations ($orgs). Run again with --org <org-id>." >&2; exit 2 ;;
  esac
fi
MCTL=(mctl)
[ -n "$ORG" ] && MCTL+=(--org "$ORG")

scrub() {  # a second guard: mask anything shaped like a key or token
  sed -E -e 's/mca_[A-Za-z0-9_-]+/mca_[REDACTED]/g' \
         -e 's/([Bb]earer )[A-Za-z0-9._~+\/=-]+/\1[REDACTED]/g' \
         -e 's/((api[_-]?key|token|password|secret)["]?[=:][ ]*["]?)[^ ",}]+/\1[REDACTED]/Ig'
}

run() {  # run <title> <command...>: print the command, then its output (stdout and stderr)
  printf '\n### %s\n$ %s\n' "$1" "${*:2}"
  "${@:2}" 2>&1 | tail -n 60 | scrub
}

{
  printf '# Multicloud support bundle\n# created %s UTC\n' "$(date -u +%FT%TZ)"
  printf '# organization %s, pool %s, offloaded namespace %s\n' "${ORG:-(only one)}" "$POOL" "$NS"
  run "mctl version"              mctl --version
  run "organizations"             sh -c "mctl auth status | grep -E '^(API URL|Method|Organizations):'"
  run "pool"                      "${MCTL[@]}" pool show "$POOL"
  run "pool diagnose"             "${MCTL[@]}" pool diagnose "$POOL"
  run "peerings"                  "${MCTL[@]}" peering list "$POOL"
  run "cloud accounts"            "${MCTL[@]}" cloud-account list
  run "support access"            "${MCTL[@]}" ssh support list

  run "kubectl context"           kubectl config current-context
  run "server version"            kubectl version
  run "connector release"         helm list -n liqo
  run "connector IDs"             sh -c "helm get values liqo-consumer -n liqo -o json | jq -r '\"clusterID=\" + (.liqo.discovery.config.clusterID // \"-\"), \"remoteClusterID=\" + (.reflectionKick.remoteClusterID // \"-\")'"
  run "liqo pods"                 kubectl -n liqo get pods -o wide
  run "liqo jobs"                 kubectl -n liqo get jobs
  run "virtual nodes"             kubectl get nodes -l liqo.io/type=virtual-node -L multicloud.io/pool
  run "virtual node conditions and taints" sh -c 'for n in $(kubectl get nodes -l liqo.io/type=virtual-node -o jsonpath="{.items[*].metadata.name}"); do echo "node $n"; kubectl get node "$n" -o jsonpath="{range .status.conditions[*]}{.type}={.status} {.reason}{\"\n\"}{end}{range .spec.taints[*]}taint {.key}={.value}:{.effect}{\"\n\"}{end}"; done'
  run "namespace offloading"      kubectl get namespaceoffloadings.offloading.liqo.io -A -o custom-columns=NS:.metadata.namespace,PHASE:.status.offloadingPhase
  run "liqo controller log"       sh -c 'kubectl -n liqo logs deploy/liqo-controller-manager --tail=300 | grep -E "^E|level=error|Required value|NamespaceMaps" | tail -n 20'
  run "workload pods"             kubectl -n "$NS" get pods -o wide
  run "workload events"           kubectl -n "$NS" get events --sort-by=.lastTimestamp -o custom-columns=TIME:.lastTimestamp,REASON:.reason,OBJECT:.involvedObject.name,MESSAGE:.message
  run "bridge pods"               kubectl -n multicloud-extend-proxy get pods -o wide
  run "bridge config"             kubectl -n multicloud-extend-proxy get configmap extend-proxy-config -o jsonpath='{.data.config\.yaml}'
  run "bridge key Secret present" kubectl -n multicloud-extend-proxy get secret extend-proxy-api-key -o name
  run "bridge log"                kubectl -n multicloud-extend-proxy logs deploy/extend-proxy --tail=40
  run "bridge events"             kubectl -n multicloud-extend-proxy get events --sort-by=.lastTimestamp -o custom-columns=TIME:.lastTimestamp,REASON:.reason,OBJECT:.involvedObject.name,MESSAGE:.message
} > "$OUT"

chmod 600 "$OUT"
echo "saved $OUT ($(wc -l < "$OUT") lines). Read it before you send it."
