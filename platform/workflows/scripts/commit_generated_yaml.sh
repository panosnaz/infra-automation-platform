#!/usr/bin/env bash
# Execution Framework -- Stage 1 (Intent), Milestone 2 support script.
#
# Commits the freshly generated NetAsCode YAML back to Git so it becomes a
# version-controlled, auditable desired-state artifact (ADR-019 Truth #2)
# instead of a local, gitignored file. Pushes with [skip ci] to avoid an
# infinite pipeline-trigger loop from this commit's own push.
#
# Usage: commit_generated_yaml.sh <path-to-generated-yaml>
#
# Requires these environment variables (already available in GitLab CI):
#   GIT_PUSH_TOKEN, CI_SERVER_HOST, CI_SERVER_PORT, CI_PROJECT_PATH,
#   CI_COMMIT_REF_NAME
set -euo pipefail

NETASCODE_YAML="$1"

git config user.email "platform-automation@lab.local"
git config user.name "Platform Automation"
git remote set-url origin "http://oauth2:${GIT_PUSH_TOKEN}@${CI_SERVER_HOST}:${CI_SERVER_PORT}/${CI_PROJECT_PATH}.git"
git add "${NETASCODE_YAML}"

if git diff --cached --quiet; then
  echo "No generated-state changes to commit"
else
  git commit -m "chore(netascode): regenerate ${NETASCODE_YAML} from Nautobot [skip ci]"
  git push origin "HEAD:${CI_COMMIT_REF_NAME}"
fi
