# Develop the SDK

The SDK primarily targets NOMAD Central. Oasis developers can use it against compatible deployments, pass supported optional REST fields where an operation exposes them, or adapt the SDK in a fork. Start with [Develop for NOMAD Oasis](oasis/index.md) to decide which path fits your deployment.

- [System architecture](architecture/index.md) explains how operations, credential acquisition, and the HTTP connection pool fit together.
- [Identity feature architecture](identity/index.md) shows the account check, failure paths, scope relationships, and timing limits.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run these commands from the repository root. Python 3.12 is used for the documentation build.

```sh
uv sync --locked --python 3.12 --group docs
uv run --offline --no-sync python -m pytest tests/unit tests/snippets
uv run --no-sync mkdocs build --strict -f mkdocs.yml
uv run --no-sync mkdocs build --strict -f mkdocs.public.yml
```

The import test and documentation snippets run offline. The combined local build writes to `site/combined/`. The public Usage build writes to `site/user/` for GitHub Pages.

To preview both guides on one server, run `uv run --no-sync mkdocs serve` and open <http://127.0.0.1:8000/>. The selector beside the GitHub link switches between Usage and Developer.

## Run the live NOMAD tests

In the repository root, create a `.env` file with the complete API base URL and a PAT with `users:read` issued by that deployment. The root `.env` is ignored by Git.

```dotenv
NOMAD_TEST_API_URL=https://nomad-lab.eu/backend/api/v1
NOMAD_TEST_PAT=
```

Fill in `NOMAD_TEST_PAT` and run the live suite explicitly:

```sh
uv run --no-sync --env-file .env python -m pytest -m integration tests/integration
```

Both live checks require `NOMAD_TEST_API_URL`. They call the same real `GET /users/me` endpoint to verify that it accepts the PAT and refuses a request without credentials. The suite neither prints account data nor changes it. The default pytest invocation excludes live tests. [Configure the live checks on GitHub](deployment.md#one-time-github-and-pypi-setup).

## Optional wheel build and verification

Run these commands from the repository root to build the distributions and populate a wheelhouse from the locked runtime dependencies. The download step needs access to the package index.

```sh
uv build
uv export --locked --no-default-groups --no-emit-project -o dist/runtime-requirements.txt
uv run --no-project --python 3.12 --with pip python -m pip download --require-hashes --only-binary=:all: -r dist/runtime-requirements.txt -d dist/wheelhouse
```

Install the built wheel offline in a clean environment and verify that the public client imports from outside the checkout. The import command should print `NomadClient`.

=== "PowerShell"

    ```powershell
    uv venv --python 3.12 .venv-smoke
    $smokePython = (Resolve-Path .venv-smoke/Scripts/python.exe).Path
    $version = uv version --short
    uv pip install --offline --no-index --find-links dist/wheelhouse --python $smokePython "dist/nomad_python_api-${version}-py3-none-any.whl"
    Push-Location ..
    try {
        & $smokePython -I -c "from nomad_python_api import NomadClient; print(NomadClient.__name__)"
    } finally {
        Pop-Location
    }
    ```

=== "macOS and Linux"

    ```sh
    uv venv --python 3.12 .venv-smoke
    smoke_python="$PWD/.venv-smoke/bin/python"
    version="$(uv version --short)"
    uv pip install --offline --no-index --find-links dist/wheelhouse --python "$smoke_python" "dist/nomad_python_api-${version}-py3-none-any.whl"
    (cd .. && "$smoke_python" -I -c 'from nomad_python_api import NomadClient; print(NomadClient.__name__)')
    ```

## Document an operation

1. Declare its method, path, and required scopes beside the operation and route requests through the shared pipeline.
2. Add a **REST endpoints used** section to the SDK guide. List every request in order and link to a REST Reference entry for each. In that entry, document the wire fields, types, required or optional status, defaults and constraints, and response or error contract.
3. Map request fields to named SDK arguments, explicit REST extension mappings, or REST-only usage. If an operation supports an Oasis-specific query, JSON, or multipart field, show where the extra goes. For example, an optional parameter added to the query of `POST /uploads` belongs in `extra_query` for an upload method that supports it. Each operation retains control of credentials, scope checks, and routing.
4. Include runnable SDK and REST examples from pytest snippets. Test the requests they send. When an extra field becomes a named option, keep the mapping form and test that providing both fails locally.

See the [branch and deployment guide](deployment.md) for the review process and CI setup.
