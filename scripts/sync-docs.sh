#!/usr/bin/env bash
# Sync the customer documentation from its authoring home into this repo.
#
# AUTHORING HOME: `docs/external/advisor/` in Multicloud's private platform
# repo, plus `docs/external/signup.md`, which four of those files link to. Edit
# there, run this, commit the result here. Never edit `docs/` in this repo by
# hand — the next sync silently overwrites it.
#
# This is a GATE, not a copy. Two checks run over the SOURCE before anything is
# written, and nothing is written unless every file passes both:
#
#   1. MARKERS. No emphasis-marked *pending*, no "to be confirmed", no
#      under-development banner. Publishing a document that still says
#      "pending" to a customer's security reviewer is worse than not
#      publishing it. Note what this does NOT flag: the word "pending" in
#      ordinary prose (a Pod that is pending, an AWS case status, a
#      `pricing_basis` enum value). The marker is the emphasis, not the word.
#
#   2. LINKS. Every relative markdown link must resolve inside the synced set.
#      A link into the private repo renders as a 404 for the reader we
#      published this for, which is the same failure as not publishing.
#
# After writing, a LEAK SWEEP runs over the result. The private repo's GitHub
# slug is a hard failure; bare private-repo file paths are listed for you to
# eyeball, because some of those citations are deliberate. This sweep used to
# be an echoed suggestion, which meant nobody ran it. It now runs.
#
# Usage:
#   scripts/sync-docs.sh                 # gate, then sync
#   scripts/sync-docs.sh --check         # gate only, write nothing
#   scripts/sync-docs.sh --from ../platform
#
# Source resolution: --from, then $MULTICLOUD_PLATFORM_REPO, then ../platform.
# Exit: 0 all checks pass, 1 any check fails or any usage error.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$REPO_ROOT/docs"
SRC_REPO="${MULTICLOUD_PLATFORM_REPO:-$REPO_ROOT/../platform}"
CHECK_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --from) SRC_REPO="$2"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    -h|--help) sed -n '2,34p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 1 ;;
  esac
done

SRC_DIR="$SRC_REPO/docs/external/advisor"
SIGNUP="$SRC_REPO/docs/external/signup.md"
[ -d "$SRC_DIR" ] || { echo "ERROR: no advisor docs at $SRC_DIR" >&2; exit 1; }
[ -f "$SIGNUP" ] || { echo "ERROR: no signup doc at $SIGNUP" >&2; exit 1; }

# Emphasis-adjacent "pending" (*pending*, **pending**, _pending_, *(pending —),
# an explicit "to be confirmed", or the under-development banner.
MARKER_RE='(\*|_)\(?[Pp]ending|[Tt]o be confirmed|Status: under development'

failed=0
files=()
while IFS= read -r f; do files+=("$f"); done < <(ls "$SRC_DIR"/*.md)
files+=("$SIGNUP")

# The set a relative link is allowed to resolve into, by basename. A
# space-delimited string rather than an associative array: macOS still ships
# bash 3.2, and a customer running this on a Mac is the common case.
KNOWN=" "
for f in "${files[@]}"; do KNOWN="$KNOWN$(basename "$f") "; done

for f in "${files[@]}"; do
  name="$(basename "$f")"

  hits="$(grep -nE "$MARKER_RE" "$f" || true)"
  if [ -n "$hits" ]; then
    echo "FAIL  markers  $name"
    echo "$hits" | sed 's/^/        /'
    failed=$((failed + 1))
  else
    echo "PASS  markers  $name"
  fi

  # Relative markdown links only: skip http(s), mailto and pure anchors.
  bad=""
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    lineno="${line%%:*}"
    target="${line#*:}"
    target="${target%%#*}"                      # drop the anchor
    [ -n "$target" ] || continue                # same-page anchor
    base="$(basename "$target")"
    case "$KNOWN" in *" $base "*) in_set=1 ;; *) in_set=0 ;; esac
    # The sync flattens two directories into one, so the three forms below all
    # land on a sibling here and are rewritten on the way out.
    if [ "$in_set" -eq 1 ] && { [ "$target" = "$base" ] \
        || [ "$target" = "../$base" ] || [ "$target" = "advisor/$base" ]; }; then
      continue
    fi
    bad="$bad        $lineno: $target"$'\n'
  done < <(grep -noE '\]\([^)#][^)]*\)' "$f" \
           | sed -E 's/\]\(//; s/\)$//' \
           | grep -vE ':(https?://|mailto:)' || true)

  if [ -n "$bad" ]; then
    echo "FAIL  links    $name"
    printf '%s' "$bad"
    failed=$((failed + 1))
  else
    echo "PASS  links    $name"
  fi
done

echo
if [ "$failed" -ne 0 ]; then
  echo "$failed check(s) failed — nothing was written to $DEST"
  echo "Fix them in the authoring home ($SRC_DIR), not here."
  exit 1
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "all checks passed (--check: nothing written)"
  exit 0
fi

mkdir -p "$DEST"
for f in "${files[@]}"; do
  # The two source directories flatten into one here, so both crossing forms
  # lose their prefix. The link gate above already proved every target lands.
  sed -e 's|](\.\./signup\.md|](signup.md|g' \
      -e 's|](advisor/|](|g' "$f" > "$DEST/$(basename "$f")"
  echo "synced  $(basename "$f")"
done
echo
echo "$(( ${#files[@]} )) file(s) synced to $DEST"

# The leak sweep, RUN rather than suggested. It used to be an echoed hint, which
# meant nobody ran it. Two needles, two severities:
#
#   1. `multicloud/platform` — the private repo's GitHub slug. A pasted URL or
#      repo reference is an unambiguous leak, so this is a hard failure.
#   2. Bare private-repo file paths (`backend/api-server/src/orgs_api.py`,
#      `advisor/src/catalog_client.py`). This is the shape that actually ships
#      and some citations are deliberate, so it LISTS them for a human rather
#      than failing. `scripts/sync-docs.sh` is excluded: that one is this repo.
echo "Verifying the synced set:"
git -C "$REPO_ROOT" diff --stat -- docs/ 2>/dev/null || true   # quiet in a non-git checkout
echo

slug_hits="$(cd "$REPO_ROOT" && grep -rn 'multicloud/platform' docs/ || true)"
if [ -n "$slug_hits" ]; then
  echo "FAIL  leak   private repo slug in the synced docs:"
  echo "$slug_hits" | sed 's/^/        /'
  echo
  echo "Fix it in the authoring home ($SRC_DIR) and re-run. Do not commit this."
  exit 1
fi
echo "PASS  leak   no 'multicloud/platform' reference"

PRIVATE_PATH_RE='(backend|advisor|common|scheduler|catalog|client|discovery|agent|data|tools|scripts|helm)/[A-Za-z0-9_./-]+\.(py|java|yaml|yml|sql|sh|tsx?|properties)'
path_hits="$(cd "$REPO_ROOT" && grep -rnoE "$PRIVATE_PATH_RE" docs/ \
             | grep -v ':scripts/sync-docs\.sh$' || true)"
if [ -n "$path_hits" ]; then
  echo "CHECK path   $(printf '%s\n' "$path_hits" | wc -l | tr -d ' ') private-repo file path citation(s)."
  echo "             Confirm each is one you meant to publish:"
  printf '%s\n' "$path_hits" | sed 's/^/        /'
else
  echo "PASS  path   no private-repo file paths cited"
fi
