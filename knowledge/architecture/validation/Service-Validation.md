---
type: architecture
domain: platform
status: active
tags: [validation]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# 03 – Service Validation

## Purpose

Service Validation verifies that business services operate correctly after infrastructure deployment.

Infrastructure health does not necessarily guarantee application functionality.

---

# Position in the Workflow

```text
Infrastructure Validation
        │
        ▼
Service Validation
```

---

# Objectives

Validate:

* End-to-end connectivity
* Application reachability
* DNS
* HTTP/HTTPS
* API availability
* Security policy behavior
* User experience

---

# Typical Checks

Examples include:

* Ping
* Traceroute
* HTTP 200 response
* API health endpoint
* DNS resolution
* TCP connectivity
* Application login
* Database connectivity

---

# Possible Technologies

* pyATS
* Python requests
* Curl
* Postman/Newman
* Custom synthetic tests
* Monitoring probes

---

# Output

Produces:

* Service availability report
* Connectivity report
* Application health summary
* Latency metrics
* Failure diagnostics

---

# Success Criteria

Business services operate according to engineering intent.
