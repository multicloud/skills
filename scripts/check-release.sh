#!/usr/bin/env bash
# Refuse to ship plugin changes that no installed copy can receive.
#
# `claude plugin update` compares VERSIONS, not content. A plugin whose files
# changed while `plugin.json`'s `version` stayed put reports "already at the
# latest version" and installs nothing -- so the fix reaches new installs only,
# and silently skips everyone who already had it. That happened three times in
# one day before anyone noticed, which is the whole reason this script exists.
#
# Run before pushing. Exit 0 means either nothing changed or the version moved.
#
#   scripts/check-release.sh              # check every plugin
#   scripts/check-release.sh <name>       # check one
#
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

fail=0

for manifest in plugins/*/.claude-plugin/plugin.json; do
  dir="$(dirname "$(dirname "$manifest")")"
  name="$(basename "$dir")"
  [ $# -eq 0 ] || [ "$1" = "$name" ] || continue

  version="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -1)"
  if [ -z "$version" ]; then
    printf 'FAIL  %-24s no "version" in %s\n' "$name" "$manifest"
    fail=1
    continue
  fi

  # The last release we tagged for this plugin, if any.
  tag="$(git tag --list "${name}--v*" --sort=-v:refname | head -1)"
  if [ -z "$tag" ]; then
    printf 'OK    %-24s %s (no previous tag -- first release)\n' "$name" "$version"
    continue
  fi

  if git diff --quiet "$tag" HEAD -- "$dir"; then
    printf 'OK    %-24s %s (unchanged since %s)\n' "$name" "$version" "$tag"
    continue
  fi

  prev="$(git show "$tag:$manifest" 2>/dev/null \
          | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"

  if [ "$version" = "$prev" ]; then
    printf 'FAIL  %-24s changed since %s, still version %s\n' "$name" "$tag" "$version"
    printf '      %s\n' "Anyone who already installed it will be told they are up to date."
    git diff --stat "$tag" HEAD -- "$dir" | sed 's/^/      /'
    printf '      %s\n' "Bump \"version\" in $manifest, then:"
    printf '      %s\n' "claude plugin tag $dir"
    fail=1
  else
    printf 'OK    %-24s %s -> %s\n' "$name" "$prev" "$version"
  fi
done

exit "$fail"
