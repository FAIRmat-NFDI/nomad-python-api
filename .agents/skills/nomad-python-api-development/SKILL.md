---
name: nomad-python-api-development
description: Plan, implement, document, and review nomad-python-api features using the maintainer's SDK design, Oasis compatibility, security, and verification practices. Use for SDK changes and architecture previews in this repository.
---

# Develop the NOMAD Python API

Read the repository's [AGENT.md](../../../AGENT.md) for the current milestone, approval gates, security requirements, and verification commands. Inspect the current branch, implementation, tests, and docs before using an earlier design decision.

## Preview an increment

- Start with the caller's workflow and confirm the actual server contract in the target deployment's OpenAPI, relevant upstream implementation, or Graph schema. Identify which behavior the SDK owns and which the server controls. Check Central and self-hosted Oasis assumptions when endpoints or identity providers differ.
- For a feature with design tradeoffs, show representative call sites, the SDK-to-REST mapping, and the proposed folder and test layout. Summarize the impact on security, request count and latency, reliability, and memory or compute. Identify what needs live or manual confirmation.
- Propose one reviewable increment with acceptance criteria. Follow the scope and manual-review gates in AGENT.md. Give exact PowerShell commands and expected results when the maintainer asks how to test on Windows. Write a meaningful Conventional Commit subject and a body explaining behavior, rationale, and verification when preparing an approved commit.

## Design the public interface

- Use an Azure-style synchronous client and domain operation groups, such as `client.identity.me()`, backed by a shared request pipeline. Keep endpoint and protocol details below the public interface. Group code, tests, examples, and docs by feature so Oasis maintainers can locate and adapt an operation in their fork.
- Keep NOMAD core data and platform operations in this SDK. Look at the existing NOMAD workflow utilities for use cases. Leave workflow authoring and orchestration to the separate workflow library.
- Keep deployment choices explicit and keyword-only. NOMAD Central is FAIRmat's hosted public deployment. A self-hosted NOMAD Oasis runs the same platform with its own configuration. For authenticated clients, choose the API endpoint through the credential and use Central when it is omitted. Keep issuer, client ID, and identity-provider hints caller-supplied. Follow the selected deployment's Keycloak configuration and use discovery when enabled by the caller.
- Support constructor options as named arguments or through `**options` where applicable. Treat deployment-specific REST extensions as a separate concern. An operation can expose explicit mappings such as `extra_query` and `extra_json` for supported request fields. Reserve the method, destination, auth, and named SDK fields. Reject duplicate values when an extension field gains a named argument.
- Register each operation's method, path, and scopes alongside its implementation. Model confirmed scope names with the SDK enum. Treat `allowed_scopes` as a local operation policy and the deployment as authoritative for token permissions. Derive any inheritance from the verified server contract. Distinguish local denial, invalid credentials, and insufficient server permissions in public errors.

## Review security and performance

| Dimension | What to check |
| --- | --- |
| Credential handling | Acquire tokens lazily. Bind token reuse to the deployment and authorization context. Keep renewals expiry-aware and share renewal work across concurrent callers. Keep credentials out of persistence, logs, errors, fixtures, and examples. Respect caller-owned token lifecycles. |
| Network and correctness | Verify TLS, validate destinations, and apply the timeout, redirect, and retry controls in AGENT.md. Check retry eligibility and mutation idempotency. Use typed, actionable errors with safe logging. |
| Latency and resource use | Reuse connection pools. Check for separate login and API round trips, N+1 reads, and unnecessary response data. Bound caches, buffers, and concurrency. Expose client pool and phase timeout settings through SDK-owned types. Treat a pool timeout as an unsent data request. Stream large transfers with bounded memory and separate inactivity and overall deadlines. |
| Lifecycle and portability | Check cleanup and failure behavior for regular Python scripts, local Jupyter kernels, and pyiron or remote workers. Keep interactive side effects tied to a documented authentication call or operation. Use scoped credentials suited to unattended execution. |

Apply the repository's license, dependency review, secret handling, and release rules. Record a specific compliance requirement when the maintainer or project identifies one.

## Document and verify the behavior

- Present public docs as a deployed SDK guide. Use a short **Summary**, runnable **Examples**, and an **API Reference**. Identify classes, methods, properties, and enums. Specify parameter types, required or optional status, defaults, return values, and actionable error cases.
- Give each public feature a worked example with prerequisites and an expected result. Show named object-style usage and options mapping or JSON setup where helpful. Link each operation to a separate REST reference with the method, route, wire fields, and where an Oasis extension maps onto the request.
- Source published executable Python from `tests/snippets/` so CI exercises the displayed code. Keep fixtures, mocks, and assertions outside the published markers. Cover successful behavior and affected failure paths offline. Use the existing authorized read-only integration suite for deployment behavior. Report automated, live, and interactive checks separately.
- Update the [Developer guide](../../../docs/dev/index.md) and [Oasis guide](../../../docs/dev/oasis/index.md) for changes that affect extension or fork authors. Use a component, sequence, activity, state, timing, or ER diagram when it explains an architectural decision or lifecycle. Keep the shared public docs build and guide selector working.
