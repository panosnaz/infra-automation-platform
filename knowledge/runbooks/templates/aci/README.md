# ACI Lab Input Templates

Fill every `FILL_ME_IN` value before asking MCP to build the scenario. Keep names consistent across all four YAML files:

- `01-fabric-access.yaml`: VLAN pools, domains, AAEPs, IPGs, leaf profiles, selectors, and port policy requirements.
- `02-tenant-application.yaml`: Tenant, VRFs, Bridge Domains, Application Profiles, EPGs, static paths, VMM bindings, and Contracts.
- `03-l3outs.yaml`: BGP/OSPF L3Outs, node profiles, interface profiles, SVI/routed interfaces, peers, and External EPGs.
- `04-ospf-and-route-leaks.yaml`: OSPF interface policies and shared-services/L3Out route leaks.

Do not add passwords, tokens, private keys, certificates, or raw OSPF/BGP authentication keys. Use `authentication_secret_ref` values that identify a Vault secret.

Recommended MCP instruction after filling these files:

```text
Read the four ACI lab YAML templates under knowledge/runbooks/templates/aci.
Validate all FILL_ME_IN values are completed and all cross-file names match.
Check Nautobot for existing objects before writing anything.
Create missing intent in dependency order using only registered MCP tools.
Do not overwrite existing objects.
Start the normal pipeline and show me the Terraform plan.
Stop before Terraform apply and ask for explicit approval.
```

The templates are planning inputs, not directly consumed by Terraform. MCP or an operator must translate them into the existing Nautobot custom-field model.
