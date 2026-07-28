---
title: "Nautobot ACI SSoT — Manual Setup Guide"
description: "Step-by-step instructions to configure Nautobot for ACI SSoT sync via the web portal"
type: runbook
domain: cisco_aci
status: active
tags: [nautobot, ssot]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# Nautobot ACI SSoT — Manual Setup Guide

This guide walks through every step required to run the **Cisco ACI Data Source** sync job in Nautobot using the web portal. No CLI or API calls are needed — everything is done through the UI.

**Environment used in this guide:**

- Nautobot: `http://localhost:8080`
- Login: `admin` / `admin`
- ACI Simulator: `https://172.30.46.103` (self-signed certificate)
- ACI credentials: `admin` / `<your-aci-password>`

---

## Prerequisites

Before starting, confirm:

- Nautobot is running and accessible at `http://localhost:8080`
- The `nautobot-ssot` plugin is installed and `enable_aci: True` is set in `PLUGINS_CONFIG` (see [Plugin Configuration](#appendix-plugin-configuration))
- The **Cisco ACI Data Source** job is enabled (see [Step 9](#step-9--enable-the-job))

---

## Overview of Objects to Create

The ACI sync job does not accept a raw URL and password in its form. Instead, it reads connection details from a chain of Nautobot objects:

```
Secrets  ──►  SecretsGroup  ──►  ExternalIntegration  ──►  Controller
                                        │                        │
                                  APIC URL + SSL      Location + Status
                                                                 │
                                                  ControllerManagedDeviceGroup
```

You will create these objects in order:

1. Location Type (if not already present)
2. Location
3. Secret — ACI Username
4. Secret — ACI Password
5. SecretsGroup + Associations
6. ExternalIntegration
7. Controller
8. ControllerManagedDeviceGroup

---

## Step 1 — Create a Location Type

> Skip this step if a **Site** location type already exists.

1. Navigate to **Organization → Location Types**
2. Click **+ Add**
3. Fill in:
   - **Name**: `Site`
   - **Nestable**: unchecked
   - **Content Types**: add `dcim | device`, `ipam | prefix`, `ipam | vlan`, `dcim | controller`
4. Click **Save**

> The `dcim | controller` content type is required — without it, the Controller cannot be placed in this location.

---

## Step 2 — Create a Location

1. Navigate to **Organization → Locations**
2. Click **+ Add**
3. Fill in:
   - **Name**: `ACI-Lab`
   - **Location Type**: `Site`
   - **Status**: `Active`
4. Click **Save**

---

## Step 3 — Create the ACI Username Secret

Secrets store credentials as references to environment variables or files — the actual value is never stored in the database.

1. Navigate to **Extras → Secrets**
2. Click **+ Add**
3. Fill in:
   - **Name**: `ACI-Username`
   - **Provider**: `Environment Variable`
   - **Variable name**: `ACI_USERNAME`
4. Click **Save**

> The environment variable `ACI_USERNAME` must be set in the Nautobot container. In the Docker Compose setup, add `ACI_USERNAME=admin` to `environments/creds.env` and restart the container.

---

## Step 4 — Create the ACI Password Secret

1. Navigate to **Extras → Secrets**
2. Click **+ Add**
3. Fill in:
   - **Name**: `ACI-Password`
   - **Provider**: `Environment Variable`
   - **Variable name**: `ACI_PASSWORD`
4. Click **Save**

> Add `ACI_PASSWORD=<your-aci-password>` to `environments/creds.env` and restart the container.

---

## Step 5 — Create a SecretsGroup and Associate the Secrets

The SecretsGroup bundles the username and password secrets together and labels their access type and role.

### 5a — Create the SecretsGroup

1. Navigate to **Extras → Secrets Groups**
2. Click **+ Add**
3. Fill in:
   - **Name**: `ACI-Credentials`
4. Click **Save**

### 5b — Add the Username Association

After saving you will be on the SecretsGroup detail page.

1. Scroll down to the **Secrets** table
2. Click **+ Add Secret Association**
3. Fill in:
   - **Secret**: `ACI-Username`
   - **Access Type**: `HTTP(S)`
   - **Secret Type**: `Username`
4. Click **Save**

### 5c — Add the Password Association

1. Click **+ Add Secret Association** again
2. Fill in:
   - **Secret**: `ACI-Password`
   - **Access Type**: `HTTP(S)`
   - **Secret Type**: `Password`
3. Click **Save**

---

## Step 6 — Create the ExternalIntegration

The ExternalIntegration holds the APIC URL, SSL settings, and a reference to the SecretsGroup.

1. Navigate to **Extras → External Integrations**
2. Click **+ Add**
3. Fill in:
   - **Name**: `ACI-Simulator-APIC`
   - **Remote URL**: `https://172.30.46.103`
   - **Verify SSL**: **unchecked** (the ACI simulator uses a self-signed certificate)
   - **Secrets Group**: `ACI-Credentials`
   - **Extra Config** (JSON): `{"tenant_prefix": "ACI"}`
4. Click **Save**

> `tenant_prefix` controls the prefix prepended to ACI tenant names when they are created in Nautobot. Leave it as `"ACI"` or change it to match your naming convention.

---

## Step 7 — Create the Controller

The Controller represents the ACI APIC in Nautobot's data model.

1. Navigate to **DCIM → Controllers**
2. Click **+ Add**
3. Fill in:
   - **Name**: `ACI-APIC`
   - **Status**: `Active`
   - **Location**: `ACI-Lab`
   - **External Integration**: `ACI-Simulator-APIC`
4. Click **Save**

---

## Step 8 — Create a ControllerManagedDeviceGroup

The sync job calls `verify_controller_managed_device_group()`, which auto-creates a group named `<controller-name> Managed Devices` if none exists. Creating it manually here gives you control over the name.

1. Navigate to **DCIM → Controller Managed Device Groups**
2. Click **+ Add**
3. Fill in:
   - **Name**: `ACI-Managed-Devices`
   - **Controller**: `ACI-APIC`
   - **Weight**: `1000`
4. Click **Save**

---

## Step 9 — Enable the Job

Jobs shipped by plugins are disabled by default and must be explicitly enabled.

1. Navigate to **Extras → Jobs**
2. Search for **Cisco ACI Data Source**
3. Click the job name to open it
4. Click **Edit** (pencil icon)
5. Check **Enabled**
6. Click **Update**

---

## Step 10 — Run the Sync

1. Navigate to **Extras → Jobs**
2. Click **Cisco ACI Data Source** → **Run**
3. Fill in the job form:
   - **ACI APIC**: select `ACI-APIC`
   - **Device(s) Location**: select `ACI-Lab` (optional — if left blank, the Controller's location is used)
   - **Dryrun**: check this on the first run to preview changes without writing to the database
   - **Debug**: optionally check for verbose logging
4. Click **Run Job Now**

### Reviewing the results

- The job will open a log output page while it runs
- After it completes, navigate to **Plugins → Single Source of Truth → Sync** to see the sync record
- A Dryrun sync shows what **would** be created/updated/deleted without committing anything
- To actually import the data, uncheck **Dryrun** and run again

---

## What Gets Imported

| ACI Object | Nautobot Object |
|---|---|
| Tenant | Tenant |
| Node (Leaf/Spine/Controller) | Device |
| Node model | Device Type |
| OOB Management IP | IP Address |
| Subnet | Prefix |
| Interface | Interface |
| VRF | VRF |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| ACI APIC dropdown is empty | No Controller exists | Complete Steps 7–8 |
| "This job is not enabled to be run" | Job is disabled | Complete Step 9 |
| `ConfigurationError: ExternalIntegration was not found` | Controller has no ExternalIntegration set | Edit the Controller and add the ExternalIntegration |
| `ConfigurationError: SecretsGroup not found` | ExternalIntegration has no SecretsGroup | Edit the ExternalIntegration and add the SecretsGroup |
| `SSL verification failed` | ACI simulator uses self-signed cert | Ensure **Verify SSL** is unchecked on the ExternalIntegration |
| `Secret value not found` / `KeyError: ACI_USERNAME` | Env var not set in container | Add `ACI_USERNAME` and `ACI_PASSWORD` to `creds.env`, restart containers |
| `Controllers may not associate to locations of type "Site"` | Location Type missing `dcim.controller` content type | Edit the Location Type and add `dcim | controller` |

---

## Appendix: Plugin Configuration

In `config/nautobot_config.py`, the following must be set before starting the containers:

```python
PLUGINS = ["nautobot_ssot"]

PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_aci": True,    # Required — ACI integration is disabled by default
    },
}
```

And in `environments/creds.env`:

```env
ACI_USERNAME=admin
ACI_PASSWORD=<your-aci-password>
```

After editing either file, restart the stack:

```bash
cd environments/
NAUTOBOT_VERSION=3.0.8 PYTHON_VER=3.12 docker compose \
  -f docker-compose.postgres.yml \
  -f docker-compose.base.yml \
  -f docker-compose.local.yml \
  restart nautobot celery_worker celery_beat
```
