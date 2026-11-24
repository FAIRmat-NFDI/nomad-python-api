# AGENTS.md — `nomad-python-api`

Repository instructions for Codex in VS Code. Follow applicable higher-priority instructions and surface any conflict that affects the task. The maintainer owns scope and approvals.

## Current milestone — scaffold only

This is the standalone Python SDK for NOMAD's core data, app, and platform operations. The intended organization is FAIRmat-NFDI. The planned PyPI distribution is `nomad-python-api` and the import package is `nomad_python_api`.

**Project boundary.** Workflow authoring, workflow YAML generation, and workflow orchestration belong to `nomad-workflow`, a separate library planned for later. Keep its implementation, migration, dependencies, and project scaffold out of this repository. The future library can use the SDK's public core API. Keep the core SDK independent of it. Use `nomad-utility-workflows` only as a reference for existing core API use cases. [Existing NOMAD utilities](https://github.com/FAIRmat-NFDI/nomad-utility-workflows)

- Start by inspecting the repository and proposing a scaffold plan. Wait for the maintainer to approve it before changing files.
- Keep the scaffold to `uv` project and build metadata, an importable `src/nomad_python_api/` package with an empty public surface, a README, an import smoke test, basic CI, and a MkDocs skeleton with separate user and developer sections.
- Use Azure and AWS Python SDK repositories as references for clear package boundaries and packaging conventions. Adopt only the conventions that fit this initial `uv` project. [Azure SDK for Python](https://github.com/Azure/azure-sdk-for-python) · [AWS SDK for Python](https://github.com/boto/boto3)
- Verify that the package builds, that it can be installed and imported, and that the docs build. The import smoke test must run offline.
- Defer SDK behavior and runtime dependencies. The approved branch and publishing workflows are described below. Client methods, endpoint calls, authentication, REST code generation, Graph queries, caching, memoization, lazy loading, and background tasks each belong in later approved iterations. Finishing the scaffold does not authorize a feature.
- The architecture and security sections describe the target for later iterations. Create packages, test infrastructure, and policies as approved work needs them.

## Agent lifecycle and approval gates

Apply these steps to features, fixes, refactors, and scaffold changes. Prioritize security, architectural fit, readable code, reliability and performance, then delivery speed. Keep changes to one logical increment and one local commit. Aim for fewer than about 200 changed lines per increment, excluding tests and docs.

1. **Plan.** Inspect the working tree, repository instructions, existing tests, and upstream API contract as applicable. Summarize the goal and ask about material unknowns. Compare the maintainer's approach with up to two useful alternatives across security, architectural fit, reliability, performance, code quality, complexity, dependencies, and testability. Recommend an approach and state the affected files, acceptance criteria, required tests, snippets, diagrams, and security implications. **Wait for explicit scope approval before editing.**
2. **Develop and test.** Work on one approved increment at a time. Preserve unrelated changes and avoid incidental refactors or formatting. Add unit tests, the public API snippet and docs, and internal UML/ER updates where required. Run the applicable checks and report the diff, failures, and exact manual test steps. **Wait for the maintainer's manual test result or explicit waiver.** Fix in-scope feedback and obtain fresh sign-off if the verified behavior changes.
3. **Test and commit.** Update `CHANGELOG.md` under Unreleased when it exists and applies, rerun the required checks for the final diff, and propose a Conventional Commit message. **Commit only after manual sign-off or waiver and explicit approval to commit.** The maintainer can give both approvals together. Stage just the reviewed increment, report its local commit hash, and continue only with approved scope.

Keep status reports short and concrete. If scope grows, pause that work and ask for approval of a revised plan. Report out-of-scope improvements and security findings. Report failed checks and your diagnosis, and keep required checks enabled. If required verification cannot run, report what is missing and obtain the maintainer's decision before committing. Obtain explicit authorization for CI, release, license, or dependency changes and before pushing, tagging, publishing, or opening a PR.

Use Conventional Commits such as `feat(uploads): add begin_create poller` or `fix(core): honor Retry-After`. Breaking changes need explicit approval, the `!` marker, and a `BREAKING CHANGE:` footer.

### Definition of done

- The accepted behavior, architecture, and relevant security controls are verified. Public APIs keep transport details internal.
- Unit tests and public API snippet tests pass. New code has at least 90% coverage once coverage is configured. The user documentation renders the tested snippet and API reference. Major changes update internal UML and relevant ER diagrams.
- Required checks pass, the applicable changelog is updated, and the maintainer has provided the required sign-off and commit approval.

## Target architecture

The design follows **Azure SDK for Python** conventions (client → operation groups → pipeline of policies;
`ItemPaged`; `LROPoller` with `begin_*` methods; a separate `aio` namespace) and
**boto3** conventions (a low-level client plus a higher-level **resource/model** layer).

### Layers

| Layer | Responsibility |
| --- | --- |
| Interfaces | Optional CLI and notebook helpers consume the public SDK. |
| Public client and models | Client lifecycle, typed operation groups, resources, lazy relationships, and QuerySet. |
| Operations | NOMAD data, app, and platform operations, paging, long-running operations, backend selection and batching. |
| Protocol | Internal typed REST request builders and Graph builders that encode structured `m_request` payloads. |
| Core | Client-owned HTTP transport and ordered policies for auth, retry, timeouts, user agent, redacted logging, and caching. |
| Schema | Transport-independent schema interpretation, dynamic sections, and units. |

**Dependency rule.** Dependencies point down through operations, protocol, and core. Keep schema interpretation independent of HTTP. Resource methods use narrow client interfaces for relationships. Keep `httpx` and generated protocol types, raw HTTP responses, and `m_request` payloads private. If the documented `client.raw` escape hatch is approved, use SDK-owned types and the same auth, destination, timeout, and redaction policies.

### Public API shape

Illustrative target for later approval. These names do not indicate implemented functionality or authorize scaffolding it.

````python
from nomad_python_api import NomadClient
from nomad_python_api.identity import EnvCredential   # azure-identity style

client = NomadClient(endpoint="prod", credential=EnvCredential())

# Operation groups (Azure style)
poller = client.uploads.begin_create("./runs/", name="Si bandgaps")   # LRO
upload = poller.result(timeout=1800)                                   # background polling

# Resource/model layer (boto3-resource style)
entry = upload.entries.first()
formula = entry.archive.results.material.chemical_formula_reduced     # lazy load

# QuerySet + data ops
df = (client.entries
        .filter(elements__all=["Si"], program="VASP")
        .select("results.material", "results.properties.electronic")
        [:500]
        .to_pandas())

# Async mirror
from nomad_python_api.aio import NomadClient as AsyncNomadClient
````

### Required architectural features

| Feature | Where | How (prefer ready-made libraries) |
|---|---|---|
| **Pipeline & policies** | `_core/pipeline.py` | An ordered set of single-purpose policies. Define what runs once per operation and what runs on each attempt. |
| **Retries** | `RetryPolicy` | `tenacity` — exponential backoff + jitter; honour `Retry-After`; retry idempotent requests only, unless documented guarantees or verified state make replay safe. |
| **Timeouts** | `TimeoutPolicy` / transport | **Every** request has connect/read timeouts (`httpx.Timeout`). No unbounded waits. |
| **Auth** | `identity/` | Credential classes (`TokenCredential`, `EnvCredential`, and `PasswordCredential` where supported) with token caching and refresh. Mirrors `azure-identity`. |
| **Paging** | `_core/paging.py` | `ItemPaged[T]` / `AsyncItemPaged[T]` hide `page_after_value`. |
| **Long-running operations** | `_core/polling.py` | `LROPoller[T]` with `.result(timeout)`, `.done()`, `.wait()`, `.cancel()`, `.status()`; polls in a **background thread** (sync) or **task** (async); uses backoff. |
| **Lazy loading** | models | Relationship and archive attributes load on first access. Explicit `.fetch()` / `.refresh()` / `prefetch=`. |
| **Memoization** | models / schema | `functools.cached_property` for derived, immutable values; `functools.lru_cache` for pure helpers. |
| **Caching** | `_core/cache.py` | `cachetools.TTLCache` in memory (per client); optional on-disk cache for schema definitions (`m_def`) and published (immutable) archives under `platformdirs.user_cache_dir` if approved and confirmed safe for public data. Scope keys by deployment, API version, and authorization context. Define size, TTL, and invalidation. Keep credentials and private payloads off disk. |
| **Identity map** | client session | The same id gives the same model instance within one client. Uses `weakref.WeakValueDictionary`. |
| **Batching / N+1 avoidance** | query planner | Lazy access on querysets is collected into one Graph query per page. |
| **Background work** | bulk ops | `concurrent.futures.ThreadPoolExecutor` (sync) / `asyncio.TaskGroup` on supported versions or a compatible async alternative with bounded concurrency for downloads and uploads. |
| **Streaming** | data ops | Generators for large result sets (`iter_archives`), streamed file downloads — constant memory. |
| **Errors** | `exceptions.py` | Hierarchy like `azure.core.exceptions`: `NomadError` → `HttpResponseError` → `ResourceNotFoundError`, `ClientAuthenticationError`, `ResourceExistsError`; plus domain errors such as `ProcessingFailedError`, `InvalidStateError`. |
| **Config** | `_config.py` | `pydantic-settings`: args > env vars (`NOMAD_*`) > config file. Deployments: `prod`, `staging`, `test`, or a custom Oasis URL. |
| **Logging** | `LoggingPolicy` | stdlib `logging`, logger name `nomad_python_api`; a **redaction filter** for tokens, passwords and `Authorization` headers. |
| **Sync + async** | `nomad_python_api` / `nomad_python_api.aio` | Same API surface. Keep shared logic in pure functions to avoid duplication. |

### Backend routing

Default to REST. Verify routes and capabilities in the target deployment's OpenAPI and Graph docs. Prefer Graph when nested reads, projections, or references reduce requests or response size. If OpenAPI generation is approved, keep it internal and record the spec and generator configuration.

| Operation | Backend |
|---|---|
| Create, upload, edit, publish, delete | REST |
| Raw file upload and download | REST |
| Processing status / polling | REST |
| Metadata search (`entries.filter`) | REST `/entries/query` |
| Nested reads (upload → entries → archive sections) | Graph `/graph/query` |
| Reference resolution, `m_def` schema | Graph |

### Model rules

- Pydantic v2 models for fixed NOMAD objects (`Upload`, `Entry`, `Dataset`, `User`).
- `Section` proxies for dynamic archive data: attribute access, `__dir__` for autocomplete, `.to_dict()`, `.to_pandas()`.
- Upload lifecycle as an explicit **state machine** (`DRAFT → UPLOADING → PROCESSING → PROCESSED | FAILED → PUBLISHED`).
  Reject transitions that are known to be invalid with `InvalidStateError` before sending a request. The service remains authoritative for lifecycle and permission checks.
- **Dirty tracking** for edits: `obj.save()` sends only the changed fields.
- Models hold a reference to their client; they never create their own HTTP sessions.
- Document when lazy access can perform I/O. Keep representations, equality, and serialization free of network access. Make polling ownership, deadlines, cancellation semantics, task cleanup, and failure reporting explicit. Measure relevant request counts, latency, or memory for performance-sensitive changes.

## Technology stack

| Purpose | Tool |
|---|---|
| Project and environment management | **uv** (`uv sync`, `uv run`, `uv add`, `uv lock`, `uv build`) |
| Build backend | `hatchling` (via `pyproject.toml`) |
| Python | Target `>=3.10`. Verify the supported NOMAD and dependency ranges before approving the scaffold and test matrix. |
| HTTP | `httpx` (sync and async) |
| Models / settings | `pydantic` v2, `pydantic-settings` |
| Retry | `tenacity` |
| Cache | `cachetools`, `platformdirs` |
| Units (archive quantities) | `pint` (optional extra) |
| Data ops | `pandas` (optional extra `[data]`) |
| Lint / format | `ruff` (incl. `S` = bandit security rules) |
| Types | `mypy --strict`. Switching to strict Pyright requires updating the CI and local commands together. |
| Tests | `pytest`, `pytest-asyncio`, `respx` (httpx mocking), `pytest-cov` |
| Security scanning | `ruff` S-rules, `pip-audit`, GitHub Dependabot |
| Docs | `mkdocs-material`, `mkdocstrings[python]`, `pymdown-extensions` (snippets, superfences/Mermaid) |
| Hooks | `pre-commit` |

**Dependency approval.** before adding a dependency, the agent proposes it in the PLAN with its license, maintenance status and why the
standard library or an existing dependency isn't enough. Runtime dependencies are kept to a minimum. Heavy libraries
(`pandas`, `pint`) go into **optional extras**.

## Target repository layout

Use the `src/` layout and take cues from Azure, AWS, and FAIRmat-NFDI. The structure below is for future approved increments. The scaffold is limited to the current milestone above. Apache-2.0 is the draft license choice and requires maintainer approval before adoption.

| Area | Target paths |
| --- | --- |
| Root | `AGENTS.md`, `README.md`, `CHANGELOG.md` (Keep a Changelog), `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml` |
| Package | `src/nomad_python_api/` with `__init__.py`, `_version.py`, `_config.py`, `_client.py`, `exceptions.py`, `identity/`, `operations/`, `models/`, `schema/`, `aio/`, and `py.typed` |
| Transport | `_core/` for pipeline, transport, paging, polling, cache, and policy modules. `_protocol/rest/` for typed requests and `_protocol/graph/` for builders and directives. |
| Tests | `tests/unit/` mirrors the package. Use `tests/integration/`, `tests/snippets/`, `tests/fixtures/`, and `tests/conftest.py` for live checks, examples, fixtures, and shared setup. |
| Docs | `docs/user/`, `docs/dev/`, `docs/internal/`, `docs/theme/`, and the three MkDocs configs below. |
| Automation | `.github/workflows/` for CI, security, docs, and release. Use `.github/PULL_REQUEST_TEMPLATE.md`, `.github/dependabot.yml`, and `scripts/check_snippet_coverage.py` when approved. |

Name private modules with a leading underscore. Export the public API deliberately from package entry points and define `__all__` in public modules. Use `begin_*` for long-running operations, `list_*` for paged results, and `get_*` for a single resource. Name operations for domain intent and keep HTTP plumbing internal.

## Code quality

- **Simple over clever.** Small functions, flat control flow, descriptive names. No metaprogramming unless it removes real complexity and the developer approves it.
- **Don't reinvent the wheel.** Use `httpx`, `tenacity`, `cachetools`, `pydantic`, `platformdirs` and stdlib (`functools`, `concurrent.futures`, `zipfile`, `pathlib`) before writing custom code.
- Use full type hints and pass `mypy --strict`. No `Any` in public signatures without a reason.
- Use keyword-only arguments for public options (`def begin_create(self, path, *, name=None, timeout=None)`).
- No global mutable state. Configuration flows through the client.
- No `print` in library code — use `logging`.
- Raise library exceptions from `exceptions.py`. Chain safe causes and suppress causes whose traceback would expose transport details or sensitive data.
- Sync and async share logic; don't copy-paste implementations.
- Keep public surface small. If it doesn't need to be public, prefix it with `_`.
- Emit `warnings.warn(..., DeprecationWarning, stacklevel=2)` and add a changelog entry for deprecations. Remove deprecated APIs only in a major release.

## Security requirements

For each change, identify the relevant trust boundaries, sensitive data, and failure modes. Consider caller inputs, deployment configuration, upstream responses, local files and caches, and CI credentials. Add focused offline tests for the controls the change relies on.

### Network and identity

- **TLS and endpoint configuration.** Use HTTPS with certificate and hostname verification. Support private CA trust through explicit configuration. Reserve plaintext HTTP for explicitly configured loopback development endpoints and warn when used. Define whether the SDK reads proxy and CA settings from the environment, and test that behavior where supported.
- **Outbound destinations and redirects.** Validate endpoint scheme, host, and port. Reject embedded credentials. Treat server-supplied pagination links, redirects, archive references, and download URLs as untrusted. Resolve relative links against the configured endpoint and validate the resulting destination before each request. Disable automatic redirects unless an operation needs them. Allow cross-origin transfers only through an operation-specific destination policy and omit NOMAD credentials on those requests.
- **Server-side embedding and SSRF.** Keep explicitly configured private Oasis deployments usable. When a server integration accepts a destination influenced by an untrusted caller or upstream response, require an administrator-controlled destination allowlist and network egress controls. Check each redirect and enforce the address policy at connection time or through a controlled egress proxy so DNS changes cannot bypass validation. Keep loopback, link-local, and cloud metadata destinations outside the allowed set unless an isolated local test explicitly needs loopback. [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- **Credentials and authorization.** Bind credentials to the intended deployment and use least-privilege scopes where available. Keep tokens scoped to their credential context and respect expiry. Use the service as the authority for access control. Require explicit calls for destructive or publishing actions. Keep secrets and private payloads out of logs, exceptions, examples, fixtures, telemetry, and disk caches. Keep `.env` files ignored by Git once local environment configuration is introduced. Redact signed URLs, query parameters, headers, and exception diagnostics. Default to read-only examples.
- **Browser integrations.** The Python client normally sends bearer tokens explicitly. If an approved browser-facing integration uses cookies for authentication, enforce CSRF controls on state-changing requests with the framework's protection and origin checks. Configure `SameSite`, `Secure`, and `HttpOnly` as appropriate. Define credentialed CORS with explicit trusted origins and enforce authorization and CSRF protection independently. [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

### Injection, files, and resource limits

- **Structured input.** Validate IDs, field names, query operators, metadata, and payload shapes at the boundary. Use HTTP parameter APIs and structured request bodies. Keep untrusted values out of shell commands, executable templates, and dynamically evaluated expressions. If invoking a subprocess is required, pass validated arguments without a shell. Parse upstream responses defensively and allow only intended fields in mutation payloads.
- **Files and archives.** Constrain local reads and writes to explicit input and output paths. If extracting archives, reject entries that escape the destination, symlinks and special files unless explicitly supported, and inputs that exceed file-count or expanded-size limits. Bound input size before parsing, parse JSON with Pydantic or the standard library, use safe YAML loading only if needed, reject unsafe deserialization of untrusted data, and stream large transfers. Preserve partial-file cleanup and avoid overwriting existing files unless the caller opts in.
- **Throttling and retries.** Enforce connection and I/O timeouts and a total deadline for multi-request operations. Bound attempts, polling, page sizes, Graph depth, worker counts, and response sizes where relevant. For retry-eligible requests, honor valid `Retry-After` and report the rate limit if the delay exceeds the operation budget. Use bounded exponential backoff with jitter for eligible transient failures without a valid server delay. Retry mutations only where documented idempotency or verified state makes repetition safe. [OWASP API security risks](https://api-security.owasp.org/editions/2023/en/0x11-t10/)

When relevant, test that a cross-origin response cannot forward credentials, an out-of-scope destination or archive path is rejected, a throttled mutation is sent only once when replay is unsafe, and a cached result cannot cross authorization contexts. Test cookie-authenticated browser integrations for rejected cross-origin state changes without a valid CSRF token.

### Dependencies and CI

- Review each new dependency's purpose, provenance, maintenance, license, and security advisories, including material transitive dependencies. Prefer the standard library or an existing maintained dependency when it fits. Keep heavier capabilities in optional extras where practical.
- Use `uv.lock` for reproducible project and CI environments. Audit the resolved dependency graph when dependency tooling is approved. Triage relevant findings before release and record any maintainer-approved exception with a reason and review date. Keep published dependency constraints compatible with supported and patched versions.
- Grant CI jobs the minimum permissions. Pin third-party GitHub Actions to reviewed full commit SHAs. Keep privileged jobs and secrets away from untrusted pull-request code and data. Approve docs deployment and PyPI release workflows separately. [GitHub Actions security guidance](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)

## Documentation and tested examples

Three documentation sets, all MkDocs-based.

### Doc 1 — User / API usage docs (`docs/user/`)

- **Style:** follow and inherit from **FAIRmat-NFDI `nomad-docs`** — same `mkdocs-material` theme configuration,
  palette, logo, `extra_css` and overrides. Copy the relevant theme config and assets into `docs/theme/` and keep a note
  of the nomad-docs commit they came from in `docs/theme/README.md`.
- Start at `docs/user/index.md`. Follow Diátaxis with `tutorials/` for learning, `how-to/` for tasks, `reference/` for API descriptions generated with mkdocstrings, and `explanation/` for concepts such as caching, routing, and migration. Give each page a primary purpose.
- Include Python examples from `tests/snippets/`. Shell commands such as `pip install` can be written directly.

### Doc 2 — Developer guide (`docs/dev/`)

For people who develop or extend the library.

- Dev environment setup (`uv sync --all-extras`, `pre-commit install`)
- Architecture rules and links to internal UML
- How to add a new operation / model / policy (step-by-step)
- Testing guide (unit vs integration vs snippets; `respx` patterns)
- Release process, versioning (SemVer), changelog rules
- Coding standards and applicable security controls

### Doc 3 — Internal UML / ER (`docs/internal/`, `mkdocs.internal.yml`)

- Diagrams in **Mermaid** (rendered by mkdocs-material and natively on GitHub): `classDiagram`, `sequenceDiagram`,
  `stateDiagram-v2`, `erDiagram`.
- Required set (kept up to date):
  - `architecture.md` — layer/component diagram
  - `models.md` — class diagram of models and relationships
  - `domain-er.md` — ER diagram of NOMAD entities (User, Upload, Entry, Archive, Dataset, App)
  - `upload-lifecycle.md` — state diagram
  - `request-pipeline.md` — sequence diagram (client → policies → transport → NOMAD)
  - `features/<feature-name>.md` — **one per major feature**
- Keep the internal site private unless the maintainer approves publication.

### Tested snippets = docs examples (mandatory)

Every new public API feature ships with at least one snippet test in `tests/snippets/`. Include the same marked source in the user docs via `pymdownx.snippets`. Fail the strict docs build on missing includes.

````python
# tests/snippets/uploads/test_create_upload.py
import pytest

@pytest.mark.snippet
def test_create_upload(client, sample_folder):
    # --8<-- [start:create_upload]
    poller = client.uploads.begin_create(sample_folder, name="My first upload")
    upload = poller.result(timeout=600)
    print(upload.upload_id, upload.state)
    # --8<-- [end:create_upload]
    assert upload.state.is_processed
````

````markdown
<!-- docs/user/how-to/upload-a-folder.md -->
```python
--8<-- "tests/snippets/uploads/test_create_upload.py:create_upload"
```
````

Keep examples reproducible.

- The code between the markers must read like **user code**: no asserts, no mocks, no test internals.
- Snippets run in CI against `respx`-mocked responses (fast, always on), and, under the `integration` marker, against the NOMAD **test** deployment.
- `scripts/check_snippet_coverage.py` fails CI if a public symbol in `__all__` has no snippet referencing it
  (allow-list via `# snippet: exempt <reason>` in the docstring only with developer approval).
- Public functions and classes need Google-style docstrings (rendered by mkdocstrings).

## Local checks and CI

For the initial scaffold, use the available checks for build, fresh install, offline import, and the docs skeleton. The full suite below applies as its tooling is approved and configured. Report unavailable checks and the reason.

```sh
uv sync --all-extras --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict src
uv run pytest -m "not integration" --cov=nomad_python_api --cov-fail-under=85
uv run python scripts/check_snippet_coverage.py
uv run mkdocs build --strict -f mkdocs.yml
uv run mkdocs build --strict -f mkdocs.public.yml
uv run mkdocs build --strict -f mkdocs.internal.yml
```

- **`ci.yml`.** Run the configured checks on PRs and pushes to `main` across supported Python versions. Keep the offline suite deterministic.
- **`security.yml`.** Once approved, run `pip-audit` and CodeQL on PRs and weekly. Use Dependabot for dependency updates.
- **Integration.** Run the approved read-only live suite against the NOMAD test deployment on trusted `develop` and `main` pushes and on manual dispatch from those branches. Keep credentials isolated from PR jobs. Additional integration targets, such as a local Oasis, require authorization.
- **Deployment.** Branch from `develop` as `dev/<name>` and open a PR back to `develop`. After manual review, promote `develop` to `main` through a PR. The first scaffold commit is the only direct-commit exception on `main`. After CI passes on a push to `develop`, deploy user docs to GitHub Pages. After CI passes on a push to `main`, publish the wheel and sdist to PyPI via Trusted Publishing. Increase the package version before each promotion. Keep developer and internal docs out of the Pages artifact. See [Branches and deployment](docs/dev/deployment.md).

## Roadmap after the scaffold

Use these phases for planning. Each increment still requires the maintainer's approval.

| Phase | Scope |
|---|---|
| **P1 Core** | config, credentials, pipeline + policies (auth, retry, timeout, logging), transport, exceptions, paging, LRO poller |
| **P2 Uploads** | `Upload` model + state machine, `begin_create` (packaging, chunked/resumable upload where supported), `wait`, `publish`, metadata edit with dirty tracking |
| **P3 Entries & Archives** | `Entry`, lazy `Archive`/`Section` proxies, schema loader (`m_def`), Graph builder |
| **P4 Query & Data ops** | `QuerySet`, query planner (REST vs Graph, batching), `to_pandas`, `iter_archives`, bulk `download` |
| **P5 Datasets, Users, Groups, Apps** | remaining core resources and documented operations |
| **P6 Core API migration** | scoped compatibility shims and migration guide for existing core API functions, subject to approval |
| **P7 Async & CLI** | `aio` namespace parity, optional CLI |

## References

- Azure SDK for Python design guidelines: https://azure.github.io/azure-sdk/python_design.html
- `azure-core` (pipeline, policies, paging, polling): https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/core/azure-core
- boto3 resources: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/resources.html
- NOMAD Graph API: https://docs.nomad-lab.eu/howto/manage/program/graph_api.html
- NOMAD REST API docs: https://nomad-lab.eu/prod/v1/api/v1/extensions/docs
- Existing core API usage reference: https://github.com/FAIRmat-NFDI/nomad-utility-workflows
- Docs style source: https://github.com/FAIRmat-NFDI/nomad-docs
- Diátaxis: https://diataxis.fr/
