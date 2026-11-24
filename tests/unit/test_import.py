def test_package_import() -> None:
    import nomad_python_api

    assert nomad_python_api.__all__ == []
