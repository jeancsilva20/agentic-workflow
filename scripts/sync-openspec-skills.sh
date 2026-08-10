#!/usr/bin/env bash
#
# Vendor the official OpenSpec skills from Fission-AI/OpenSpec at a pinned commit.
#
# This is an *explicit* maintenance step. Nothing in the agent runtime calls it:
# a run must never reach out to GitHub to decide which instructions guide it.
# The pristine upstream copies land in openspec/vendor/openspec-skills/ and the
# provenance is recorded in openspec/openspec-version.yaml.
#
# The skills served to the agent live in agent/skills/ and are *ports*, not
# copies: every upstream skill declares `compatibility: Requires openspec CLI`
# and there is no openspec binary in the sandbox (design.md Decision 4). This
# script therefore never overwrites agent/skills/ — it refreshes the vendored
# reference and tells you which ported skill each upstream file maps to, so the
# reconciliation stays a human decision instead of a silent breakage.
#
# Usage:
#   scripts/sync-openspec-skills.sh --commit <SHA> [--version <tag>]
#
set -euo pipefail

REPO="Fission-AI/OpenSpec"
COMMIT=""
VERSION=""

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${ROOT_DIR}/openspec/vendor/openspec-skills"
MANIFEST="${ROOT_DIR}/openspec/openspec-version.yaml"

die() {
  echo "error: $*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
usage: scripts/sync-openspec-skills.sh --commit <SHA> [--version <tag>]

  --commit   Full 40-character commit SHA of Fission-AI/OpenSpec to vendor.
             REQUIRED. There is no default and no fallback to main: an
             unpinned sync would silently change the instructions the agent
             follows between runs.
  --version  Human-readable tag for the manifest (e.g. v1.8.0). Optional;
             recorded as "unpinned-tag" when omitted.
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --commit)
      [[ $# -ge 2 ]] || usage
      COMMIT="$2"
      shift 2
      ;;
    --version)
      [[ $# -ge 2 ]] || usage
      VERSION="$2"
      shift 2
      ;;
    -h | --help) usage ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "${COMMIT}" ]] || {
  echo "error: --commit is required (never sync from main)" >&2
  usage
}
[[ "${COMMIT}" =~ ^[0-9a-f]{40}$ ]] || die "--commit must be a full 40-character SHA, got: ${COMMIT}"

command -v curl >/dev/null || die "curl is required"
command -v python3 >/dev/null || die "python3 is required"

echo "Fetching skill list from ${REPO}@${COMMIT} ..."
TREE_JSON="$(curl -fsSL "https://api.github.com/repos/${REPO}/git/trees/${COMMIT}?recursive=1")" ||
  die "failed to read the tree for ${COMMIT} — is the SHA correct and reachable?"

mapfile -t SKILL_PATHS < <(printf '%s' "${TREE_JSON}" | python3 -c '
import json, sys
tree = json.load(sys.stdin).get("tree", [])
paths = sorted(
    entry["path"]
    for entry in tree
    if entry.get("type") == "blob"
    and entry["path"].startswith("skills/")
    and entry["path"].endswith("/SKILL.md")
)
print("\n".join(paths))
')

[[ ${#SKILL_PATHS[@]} -gt 0 ]] || die "no skills/*/SKILL.md found at ${COMMIT} — refusing to write an empty vendor tree"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

for path in "${SKILL_PATHS[@]}"; do
  name="$(basename "$(dirname "${path}")")"
  mkdir -p "${TMP_DIR}/${name}"
  curl -fsSL "https://raw.githubusercontent.com/${REPO}/${COMMIT}/${path}" \
    -o "${TMP_DIR}/${name}/SKILL.md" ||
    die "failed to fetch ${path} at ${COMMIT}"
  echo "  fetched ${name}"
done

curl -fsSL "https://raw.githubusercontent.com/${REPO}/${COMMIT}/skills/README.md" \
  -o "${TMP_DIR}/README.md" || die "failed to fetch skills/README.md at ${COMMIT}"

rm -rf "${VENDOR_DIR}"
mkdir -p "$(dirname "${VENDOR_DIR}")"
cp -R "${TMP_DIR}" "${VENDOR_DIR}"

FETCHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
VERSION="${VERSION:-unpinned-tag}"

{
  cat <<EOF
# Provenance of the OpenSpec instructions this agent follows.
#
# Written by scripts/sync-openspec-skills.sh — do not hand-edit. Re-run the
# script with a new --commit to update. Nothing at runtime fetches OpenSpec;
# this file is the audit trail for which upstream revision guided a run.

source: https://github.com/${REPO}
version: "${VERSION}"
commit: ${COMMIT}
fetched_at: ${FETCHED_AT}

# Pristine upstream copies, refreshed by the sync script.
vendor_dir: openspec/vendor/openspec-skills

skill_files:
EOF
  for path in "${SKILL_PATHS[@]}"; do
    name="$(basename "$(dirname "${path}")")"
    echo "  - name: ${name}"
    echo "    upstream_path: ${path}"
    echo "    vendored_to: openspec/vendor/openspec-skills/${name}/SKILL.md"
  done
  cat <<'EOF'

# Skills actually served to the agent (agent/skills/, route /openspec-skills/).
# These are ports, not copies: upstream drives the `openspec` CLI, which does
# not exist in the sandbox (design.md Decision 4). The sync script never
# overwrites them — after a sync, diff the vendored file against its port and
# decide what to carry over by hand.
ported_skills:
  - name: openspec-explore
    ported_from: openspec-explore
  - name: openspec-propose
    ported_from: openspec-new-change + openspec-propose
  - name: openspec-verify
    ported_from: openspec-verify-change
  - name: openspec-archive
    ported_from: openspec-archive-change
EOF
} >"${MANIFEST}"

echo
echo "Vendored ${#SKILL_PATHS[@]} skill(s) to ${VENDOR_DIR#"${ROOT_DIR}/"}"
echo "Updated ${MANIFEST#"${ROOT_DIR}/"} (version=${VERSION}, commit=${COMMIT})"
echo
echo "Ported skills in agent/skills/ were NOT touched. Reconcile by hand:"
echo "  agent/skills/openspec-explore  <- vendor/openspec-skills/openspec-explore"
echo "  agent/skills/openspec-propose  <- vendor/openspec-skills/openspec-new-change, openspec-propose"
echo "  agent/skills/openspec-verify   <- vendor/openspec-skills/openspec-verify-change"
echo "  agent/skills/openspec-archive  <- vendor/openspec-skills/openspec-archive-change"
