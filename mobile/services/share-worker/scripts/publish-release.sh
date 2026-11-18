#!/usr/bin/env bash
# Agent Phone Android releases are GitHub-only. Inherited upload routes are disabled.
set -euo pipefail

usage() {
  echo "usage: $0 <dist dir> --dry-run|--draft|--publish" >&2
  exit 2
}
die() { printf 'publish: %s\n' "$*" >&2; exit 1; }
[[ $# == 2 ]] || usage
case "$2" in --dry-run|--draft|--publish) mode=$2 ;; *) usage ;; esac
DIST=$(cd "$1" && pwd -P) || usage
MOBILE=$(cd "$(dirname "$0")/../../.." && pwd -P)
REPO=aqing520/agent-phone
GH_REPO=github.com/$REPO

# Validate before reading credentials, contacting a server, or writing anything remotely.
plan=$(PYTHONDONTWRITEBYTECODE=1 python3 "$MOBILE/tooling/release_assets.py" --verify-dist "$DIST") || die "release preflight failed"
{
  IFS= read -r TAG
  IFS= read -r COMMIT
  files=()
  while IFS= read -r name; do files+=("$name"); done
} <<<"$plan"
VERSION=${TAG#v}
BASE="https://github.com/$REPO/releases/download/$TAG"
if [[ "$mode" == --dry-run ]]; then
  printf 'Agent Phone %s → %s (GitHub only)\n' "$TAG" "$REPO"
  printf 'Source commit: %s\n' "$COMMIT"
  printf 'Asset: %s\n' "${files[@]}"
  printf 'Dry run: local checks passed; no network or uploads.\n'
  exit 0
fi

command -v gh >/dev/null || die 'gh is required'
gh_() { GH_HOST=github.com gh "$@"; }
api() { gh_ api --hostname github.com "$@"; }
[[ $(gh_ repo view "$GH_REPO" --json visibility --jq .visibility) == PUBLIC ]] || die 'GitHub release and corresponding source require the public Agent Phone repository'
ref=$(api "repos/$REPO/git/ref/tags/$TAG" --jq '[.object.type, .object.sha] | join(" ")') || die "push and verify the exact source tag $TAG before publishing"
# Annotated tags refer to a tag object; lightweight tags refer straight to a commit.
for attempt in 1 2 3 4 5; do
  read -r kind sha <<<"$ref"
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die 'unexpected GitHub tag object'
  [[ "$kind" == tag ]] || break
  ref=$(api "repos/$REPO/git/tags/$sha" --jq '[.object.type, .object.sha] | join(" ")')
done
[[ "$kind" == commit && "$sha" == "$COMMIT" ]] || die "GitHub tag $TAG does not point to APK source commit $COMMIT"

# A private scratch directory for the generated notes and readback verification.
TMP=$(mktemp -d)
trap '[[ -n "$TMP" && -d "$TMP" && "$TMP" != / ]] && rm -rf -- "$TMP"' EXIT
python3 - "$DIST/update.json" "$BASE" "$COMMIT" >"$TMP/notes.md" <<'PY'
import json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_bytes())
base, commit = sys.argv[2:]
print(f"**Android:** [{manifest['assets']['arm64']['name']}]({base}/{manifest['assets']['arm64']['name']})")
print(f"\n**对应源码 / Corresponding source:** [exact source and build scripts](https://github.com/aqing520/agent-phone/archive/{commit}.zip), "
      f"[source directions]({base}/SOURCE.md), [third-party corresponding source]({base}/THIRD_PARTY_SOURCES.md).")
print(f"\n**许可证 / Licenses:** [AGPL-3.0]({base}/LICENSE.txt), [third-party notices]({base}/THIRD_PARTY_NOTICES.md).")
if manifest.get('notes', '').strip():
    print('\n' + manifest['notes'])
PY

paths=()
for name in "${files[@]}"; do paths+=("$DIST/$name"); done
# Refuse to overwrite or add files to any existing release. Complete an existing
# draft only if the exact notes and every asset agree. Never edit live releases.
if draft=$(gh_ release view "$TAG" --repo "$GH_REPO" --json isDraft,body); then
  python3 - "$TMP/notes.md" "$draft" <<'PY' || die 'existing release is not a matching draft; refusing to change it'
import json, sys
from pathlib import Path
release = json.loads(sys.argv[2])
if not release['isDraft'] or release['body'].strip() != Path(sys.argv[1]).read_text().strip():
    sys.exit(1)
PY
else
  pre=()
  if [[ "$VERSION" == *-* ]]; then pre=(--prerelease); fi
  # The GitHub API rejects conflicting release creation instead of overwriting it.
  gh_ release create "$TAG" "${paths[@]}" --repo "$GH_REPO" --verify-tag --draft \
    --title "Agent Phone $VERSION" --notes-file "$TMP/notes.md" ${pre[@]+"${pre[@]}"}
fi

mkdir "$TMP/readback"
gh_ release download "$TAG" --repo "$GH_REPO" --dir "$TMP/readback"
python3 - "$DIST" "$TMP/readback" "${files[@]}" <<'PY' || die 'GitHub draft assets do not exactly match the verified release directory'
import hashlib, sys
from pathlib import Path
local, remote = map(Path, sys.argv[1:3])
expected = set(sys.argv[3:])
if {f.name for f in remote.iterdir()} != expected:
    sys.exit('unexpected or missing GitHub draft assets')

def digest(file):
    with file.open('rb') as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
        return h.digest()

for name in expected:
    if digest(local / name) != digest(remote / name):
        sys.exit(f'{name}: SHA-256 differs')
PY
if [[ "$mode" == --publish ]]; then
  gh_ release edit "$TAG" --repo "$GH_REPO" --draft=false
else
  printf 'Verified draft %s on %s; not published.\n' "$TAG" "$REPO"
fi
