# Develop for NOMAD Oasis

Start here if you maintain an Oasis, an institute-specific NOMAD deployment, or a fork of the NOMAD server. This SDK primarily targets **NOMAD Central**. It also works with an Oasis when the deployment exposes the REST contract used by the SDK and accepts the credential for that deployment. The REST appendix names the routes to compare with your Oasis's own Swagger or OpenAPI document. [NOMAD Oasis configuration](https://docs.nomad-lab.eu/howto/oasis/configure.html)

## Choose how to integrate

| Your deployment | SDK approach |
| --- | --- |
| The same REST route, request, response, and scope as Central | Use the standard SDK. Set the complete HTTPS API v1 base URL and use a credential issued for the Oasis. Set `ca_bundle` if the Oasis uses a private CA. |
| The same route with an optional institute-specific field | Check the SDK method's **REST endpoints used** section. Use `extra_query`, `extra_json`, or a multipart mapping if that method exposes it for the relevant part of the request. |
| A different route, request encoding, response shape, or authorization contract | Use a deployment-specific adapter or fork the SDK. Keep the change close to the affected operation and retain the shared request policy. |
| An API plugin on a separate route | Use a dedicated integration or add a typed operation in your fork. Plugin routes can be mounted separately from the core API. [NOMAD API plugins](https://docs.nomad-lab.eu/howto/plugins/types/apis.html) |

The core SDK and the NOMAD server are separate projects. A change in an Oasis server fork affects what that server accepts. A change in the SDK controls the request your Python application sends and how it reads the response. For a federated Oasis, configure the API URL of the deployment you intend to call and use its credential. The client sends requests only to that configured deployment.

## Trace a method to your Oasis

1. Find the method in the user guide and follow **REST endpoint used** to the reference. It gives the wire path, method, scopes, request fields, and response mapping.
2. Open the OpenAPI document for the Oasis you actually target. Compare the route including method, the input location and media type, and the response schema. Verify the scope in your deployment's docs or server code if OpenAPI does not declare it.
3. If the contracts match, configure the client with the full deployment API base URL. For identity, confirm that `GET /users/me` accepts the intended bearer credential with `users:read`. The SDK maps a non-empty user ID and an optional username into `Account`.
4. For an optional extension, put the value in the mapping that corresponds to its wire location. A custom query parameter belongs in `extra_query` when the operation supports it. A JSON object field belongs in `extra_json`. Adding a field to the client constructor does not put it in a REST request.

For example, if a future upload method wraps `POST /uploads` and your Oasis documents a query parameter named `c`, that method could accept `extra_query={"c": "institute-value"}`. Verify the placement in your Oasis contract. The current identity account call takes no extension fields because its REST request has no query parameters or body.

An extension value cannot replace the operation's HTTP method, URL, credential, scope requirements, or SDK-owned input fields. When upstream promotes an extension field to a named argument, keep accepting the old mapping form and reject calls that supply both forms.

## Example: extend a JSON request body

This offline example illustrates a hypothetical Oasis endpoint that accepts a JSON object. The wrapper provides the named `name` argument. The caller passes the institute-specific `institute_tag` field through the named `extra_json` keyword. Both fields appear at the top level of the resulting REST body. Supplying `name` through both arguments raises an error before HTTP.

```python
--8<-- "tests/snippets/test_rest_extensions.py:extra_json_demo"
```

This example only builds a payload. It makes no request and uses no token. CI checks the JSON encoding and duplicate-field rejection. When an upload extension ships, replace this example with the real SDK method and document the field's actual wire location in the upload method's REST reference.

## Set up a fork

Fork [FAIRmat-NFDI/nomad-python-api](https://github.com/FAIRmat-NFDI/nomad-python-api) on GitHub. Replace `YOUR_ORG` below with the owner of the fork.

```sh
git clone https://github.com/YOUR_ORG/nomad-python-api.git
cd nomad-python-api
git remote add upstream https://github.com/FAIRmat-NFDI/nomad-python-api.git
git fetch upstream
git switch --no-track -c dev/oasis-customization upstream/develop
uv sync --locked --python 3.12 --group docs
```

Review the fork's workflow and environment settings before enabling deployments. The upstream workflow includes Pages and PyPI jobs for its release branches. Set up the fork's own publication destinations if it needs to publish. See [Branches and deployment](../deployment.md) for the upstream review and promotion flow.

## Locate the change

| Change | Where to work |
| --- | --- |
| Change the identity route or how its response maps to the account | `src/nomad_python_api/identity/_operations.py` and, if the returned model changes, `identity/_account.py`. |
| Add a typed operation for a different resource | Add a feature package alongside `identity/`. Keep each route, transport inputs, and required scopes together, then attach the operation group through `_client.py`. |
| Update deployment binding or a shared HTTP rule | Review `src/nomad_python_api/_core/` and its security tests first. Changes here affect every feature using the pipeline. |
| Change an example or the REST contract page | Update the feature's snippets under `tests/snippets/`, its public guide and REST reference under `docs/user/`, and its architecture notes under `docs/dev/`. |

Start with the [system architecture](../architecture/index.md) for dependency direction and the [identity architecture](../identity/index.md) for a complete example. Keep fork-only behavior in the relevant operation or response mapper so the public imports and security controls stay stable. The current pipeline sends a bodyless identity request. When a new operation needs inputs, add explicit, typed query or body handling to the pipeline and keep the feature's serialization rules beside its operation declaration.

## Verify and maintain the fork

1. Add an offline test that asserts the exact HTTP method, URL, scopes, and placement of custom fields. Include an error case such as a denied scope, a conflicting field, or a response that violates the local contract.
2. Include the tested Python example and link **REST endpoints used** to the deployment-specific reference. Record the Oasis version or contract the example was checked against. Run the [local test and docs commands](../index.md).
3. Before publishing to colleagues, install the wheel into their target Python environment. Run a read-only smoke test on the intended Oasis using a locally supplied least-privilege credential. Put only fake tokens and synthetic responses in CI fixtures.
4. Periodically fetch `upstream`, reconcile the feature-specific changes, and rerun the request, wheel, and strict docs checks before releasing a new fork version.
