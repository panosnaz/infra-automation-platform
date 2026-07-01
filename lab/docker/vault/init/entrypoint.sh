#!/bin/sh
# vault-entrypoint.sh
# Starts Vault server, auto-initialises on first run, unseals on every run,
# and populates all lab secrets. Runs inside the hashicorp/vault container.
set -e

VAULT_ADDR="http://127.0.0.1:8200"
KEYS_FILE="/vault/state/vault-keys.txt"

# ---------------------------------------------------------------------------
# 1. Start vault server in background
# ---------------------------------------------------------------------------
echo "[vault-init] Starting Vault server..."
vault server -config=/vault/config/vault.hcl &
VAULT_PID=$!

# ---------------------------------------------------------------------------
# 2. Wait for the API to become reachable
# ---------------------------------------------------------------------------
echo "[vault-init] Waiting for Vault API..."
until vault status 2>&1 | grep -q "Initialized"; do
  sleep 2
done
echo "[vault-init] Vault API is reachable."

# ---------------------------------------------------------------------------
# 3. Initialise on first run (creates unseal key + root token)
# ---------------------------------------------------------------------------
if vault status 2>&1 | grep -q "Initialized.*false"; then
  echo "[vault-init] First run — initialising Vault (key-shares=1, threshold=1)..."
  # Use default (text) format — much simpler to parse than JSON in a minimal shell
  vault operator init \
    -key-shares=1 \
    -key-threshold=1 \
    > "${KEYS_FILE}"

  echo "[vault-init] Keys saved to ${KEYS_FILE}."
fi

# ---------------------------------------------------------------------------
# 4. Unseal if sealed (every restart)
# ---------------------------------------------------------------------------
if vault status 2>&1 | grep -q "Sealed.*true"; then
  echo "[vault-init] Unsealing Vault..."
  UNSEAL_KEY=$(grep "^Unseal Key 1:" "${KEYS_FILE}" | awk '{print $NF}')
  vault operator unseal "${UNSEAL_KEY}"
  echo "[vault-init] Vault unsealed."
fi

# ---------------------------------------------------------------------------
# 5. Read root token for subsequent operations
# ---------------------------------------------------------------------------
ROOT_TOKEN=$(grep "^Initial Root Token:" "${KEYS_FILE}" | awk '{print $NF}')
echo "[vault-init] Vault is initialised and unsealed."
echo "[vault-init] UI : http://localhost:8200/ui"
echo "[vault-init] Token: ${ROOT_TOKEN}"

# ---------------------------------------------------------------------------
# 6. Enable KV v2 at secret/ (idempotent)
# ---------------------------------------------------------------------------
VAULT_TOKEN="${ROOT_TOKEN}" vault secrets list 2>/dev/null | grep -q "^secret/" || \
  VAULT_TOKEN="${ROOT_TOKEN}" vault secrets enable -path=secret kv-v2
echo "[vault-init] KV v2 engine active at secret/."

# ---------------------------------------------------------------------------
# 7. Populate lab secrets (only on first run)
# ---------------------------------------------------------------------------
if ! VAULT_TOKEN="${ROOT_TOKEN}" vault kv get secret/lab/nautobot >/dev/null 2>&1; then
  echo "[vault-init] Writing lab secrets..."

  # Nautobot service credentials
  VAULT_TOKEN="${ROOT_TOKEN}" vault kv put secret/lab/nautobot \
    db_password="changeme" \
    redis_password="changeme" \
    secret_key="012345678901234567890123456789012345678901234567890123456789" \
    superuser_password="admin" \
    superuser_api_token="0123456789abcdef0123456789abcdef01234567"

  # ACI Simulator credentials
  VAULT_TOKEN="${ROOT_TOKEN}" vault kv put secret/lab/aci \
    username="admin" \
    password="Admin123" \
    url="https://172.30.46.103" \
    insecure="true"

  # Platform tooling (Terraform, generator, Ansible, pyATS)
  VAULT_TOKEN="${ROOT_TOKEN}" vault kv put secret/lab/platform \
    nautobot_url="http://nautobot:8080" \
    nautobot_api_token="0123456789abcdef0123456789abcdef01234567" \
    aci_url="https://172.30.46.103" \
    aci_username="admin" \
    aci_password="Admin123"

  echo "[vault-init] All secrets written."
  echo "[vault-init] Paths: secret/lab/nautobot | secret/lab/aci | secret/lab/platform"
else
  echo "[vault-init] Secrets already present — skipping population."
fi

echo "[vault-init] Setup complete. Vault is ready."

# ---------------------------------------------------------------------------
# 8. Keep container alive (hand off to vault server process)
# ---------------------------------------------------------------------------
wait "${VAULT_PID}"
