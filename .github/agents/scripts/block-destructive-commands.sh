#!/usr/bin/env bash
# PreToolUse hook for the Network Platform Operator agent.
# Denies destructive/irreversible shell commands, file writes via shell
# redirection (this agent has no `edit` tool -- redirection is the one way
# `execute` could still write files), and mutating HTTP calls (curl/wget with
# POST/PUT/PATCH/DELETE or a request body) that would bypass the MCP tools
# and write to Nautobot/GitLab directly. Best-effort: parses common
# PreToolUse payload shapes; the agent's own instructions are the primary
# safety mechanism, this is a deterministic backstop, not a guarantee.
set -euo pipefail

input="$(cat)"

command="$(python3 - "$input" <<'PY' 2>/dev/null || true
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    print("")
    sys.exit(0)
tool_input = data.get("tool_input") or data.get("toolInput") or data.get("parameters") or {}
cmd = tool_input.get("command") or tool_input.get("cmd") or ""
print(cmd)
PY
)"

if [ -z "$command" ]; then
  exit 0
fi

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": %s}}\n' \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$reason")"
  exit 0
}

# 1. Known-destructive commands.
deny_patterns=(
  'docker[[:space:]]+compose([[:space:]]|.)*down'
  'terraform[[:space:]]+(apply|destroy)'
  'git[[:space:]]+push([[:space:]].*)?(--force|-f)([[:space:]]|$)'
  'git[[:space:]]+reset[[:space:]]+--hard'
  'rm[[:space:]]+-rf'
  'docker[[:space:]]+(stop|rm|kill|volume[[:space:]]+rm|system[[:space:]]+prune)'
  'vault[[:space:]]+(operator|kv[[:space:]]+put|kv[[:space:]]+delete)'
  'gitlab-rails[[:space:]]+runner'
  'trigger/pipeline'
)
for pattern in "${deny_patterns[@]}"; do
  if echo "$command" | grep -qiE "$pattern"; then
    deny "Blocked: command matches denied destructive pattern '${pattern}'. Infrastructure changes must go through create_tenant/create_vrf/etc. and the GitLab pipeline, never direct commands."
  fi
done

# 2. File writes via shell redirection -- this agent has no `edit` tool;
#    closing this gap so `execute` can't be used to write/modify files instead.
if echo "$command" | grep -qE '(^|[^>])>{1,2}[^>]|[[:space:]]tee[[:space:]]'; then
  if ! echo "$command" | grep -qE '>[[:space:]]*/dev/null'; then
    deny "Blocked: command writes to a file via shell redirection/tee. This agent has no file-editing tool by design -- read-only diagnostics only."
  fi
fi

# 3. Mutating HTTP calls (curl/wget) -- prevents bypassing the MCP tools by
#    hitting Nautobot/GitLab's write endpoints directly.
if echo "$command" | grep -qiE '(curl|wget)'; then
  if echo "$command" | grep -qiE -- '-X[[:space:]]*(POST|PUT|PATCH|DELETE)|--request[[:space:]]+(POST|PUT|PATCH|DELETE)|[[:space:]](-d|--data|-F|--form)([[:space:]]|=)'; then
    deny "Blocked: mutating HTTP call (POST/PUT/PATCH/DELETE or a request body) detected. Infrastructure writes must go through the MCP tools (create_tenant/create_vrf/etc.), never a direct API call."
  fi
fi

exit 0
