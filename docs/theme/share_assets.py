"""Publish the shared NOMAD stylesheet and favicon in each docs build."""

from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files


def on_files(files: Files, config: MkDocsConfig) -> Files:
    assets = Path(__file__).resolve().parent
    shared_assets = [
        ("extra.css", "stylesheets/extra.css"),
        ("favicon.png", "assets/favicon.png"),
    ]
    if config.extra.get("guide_switcher"):
        shared_assets.extend([
            ("guide-switcher.css", "stylesheets/guide-switcher.css"),
            ("guide-switcher.js", "javascripts/guide-switcher.js"),
        ])

    for source, destination in shared_assets:
        existing = files.get_file_from_path(destination)
        if existing is not None:
            files.remove(existing)
        files.append(File.generated(config, destination, abs_src_path=str(assets / source)))
    return files
