# NOMAD Python API

`nomad-python-api` is the Python SDK for core NOMAD data, app, and platform operations.

## Install and import

Use Python 3.10 or later.

### Install from PyPI

Activate your project's virtual environment and install the SDK.

```sh
python -m pip install nomad-python-api
python -c "import nomad_python_api"
```

To install a published prerelease, use `python -m pip install --pre nomad-python-api`.

### Use a Git checkout

Activate your project's virtual environment and run these commands from your project's root. The editable install uses the SDK source from the sibling checkout.

```sh
git clone https://github.com/FAIRmat-NFDI/nomad-python-api.git ../nomad-python-api
python -m pip install -e ../nomad-python-api
python -c "import nomad_python_api"
```

The [Developer Guide](docs/dev/index.md) covers testing and the optional wheel build.

## Build the docs

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for local development and docs builds.

```sh
uv sync --locked --python 3.12 --group docs
uv run --no-sync mkdocs build --strict -f mkdocs.yml
uv run --no-sync mkdocs build --strict -f mkdocs.dev.yml
```

Open `site/user/index.html` for the user guide and `site/dev/index.html` for the developer guide.

Both guides use the shared NOMAD Material theme. See [Branches and deployment](docs/dev/deployment.md) for the review flow, GitHub Pages, and PyPI setup.
