# Develop the SDK

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run these commands from the repository root. Python 3.12 is used for the documentation build.

```sh
uv sync --locked --python 3.12 --group docs
uv run --offline --no-sync python -m pytest tests/unit tests/snippets
uv run --no-sync mkdocs build --strict -f mkdocs.yml
uv run --no-sync mkdocs build --strict -f mkdocs.dev.yml
```

The import test and documentation snippets run offline. The two docs builds write to `site/user/` and `site/dev/`.

## Optional wheel build and verification

Run `uv build` from the repository root to create a wheel and source distribution in `dist/`. To verify the wheel, install it offline in a clean environment and import it from outside the checkout. The import command should print `[]`.

=== "PowerShell"

    ```powershell
    uv venv --python 3.12 .venv-smoke
    $smokePython = (Resolve-Path .venv-smoke/Scripts/python.exe).Path
    $version = uv version --short
    uv pip install --offline --no-index --python $smokePython "dist/nomad_python_api-${version}-py3-none-any.whl"
    Push-Location ..
    try {
        & $smokePython -I -c "import nomad_python_api; print(nomad_python_api.__all__)"
    } finally {
        Pop-Location
    }
    ```

=== "macOS and Linux"

    ```sh
    uv venv --python 3.12 .venv-smoke
    smoke_python="$PWD/.venv-smoke/bin/python"
    version="$(uv version --short)"
    uv pip install --offline --no-index --python "$smoke_python" "dist/nomad_python_api-${version}-py3-none-any.whl"
    (cd .. && "$smoke_python" -I -c 'import nomad_python_api; print(nomad_python_api.__all__)')
    ```

See the [branch and deployment guide](deployment.md) for the review process and CI setup.
