# Getting started

The NOMAD Python API is the Python SDK for core NOMAD data, app, and platform operations. It primarily targets NOMAD Central and also supports Oasis deployments with compatible REST endpoints.

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

Activate your project's virtual environment and run these commands from your project's root. The clone creates a sibling directory, and the editable install makes the SDK available to your project. Changes to Python files in the checkout take effect on the next run.

```sh
git clone https://github.com/FAIRmat-NFDI/nomad-python-api.git ../nomad-python-api
python -m pip install -e ../nomad-python-api
python -c "import nomad_python_api"
```

After either install, use `import nomad_python_api` in your project code.

See the [Authentication guide](identity/index.md) to connect to a deployment and check your account.

## CLI

Run these commands in your project's activated Python environment. `pydoc` shows the package documentation, and `__all__` lists the names explicitly exported at the package root.

```sh
python -m pydoc nomad_python_api
python -c "import nomad_python_api as nomad; print(nomad.__all__)"
```

To see the exported names with their descriptions, start `python` and paste the example below. The list covers top-level exports. Use the API's documented import path to find a specific submodule.

```python
--8<-- "tests/snippets/test_discover_api.py:discover_api"
```

Use `help(obj)` to display full interactive help for a Python object or `inspect.getdoc(obj)` to read its docstring as text.
