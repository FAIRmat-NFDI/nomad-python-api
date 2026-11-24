"""Publish the shared NOMAD stylesheet and favicon in each docs build."""

from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files


def on_files(files: Files, config: MkDocsConfig) -> Files:
    assets = Path(__file__).resolve().parent
    for source, destination in (
        ("extra.css", "stylesheets/extra.css"),
        ("favicon.png", "assets/favicon.png"),
    ):
        files.append(File.generated(config, destination, abs_src_path=str(assets / source)))
    return files
