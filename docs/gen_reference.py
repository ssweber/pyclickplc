"""Generate MkDocs API reference pages for pyclickplc modules."""

from pathlib import Path

import mkdocs_gen_files

PACKAGE = "pyclickplc"
ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src" / PACKAGE

overview_lines = [
    "# API Reference",
    "",
    "This section is generated from source using `mkdocstrings`.",
    "",
    "## Modules",
]

for module_path in sorted(SRC_DIR.glob("*.py")):
    if module_path.name == "__main__.py":
        continue

    if module_path.name == "__init__.py":
        identifier = PACKAGE
        doc_rel_path = Path("reference/api") / f"{PACKAGE}.md"
    else:
        identifier = f"{PACKAGE}.{module_path.stem}"
        doc_rel_path = Path("reference/api") / f"{module_path.stem}.md"

    with mkdocs_gen_files.open(doc_rel_path, "w") as fd:
        fd.write(f"::: {identifier}\n")

    mkdocs_gen_files.set_edit_path(doc_rel_path, module_path.relative_to(ROOT))
    overview_lines.append(f"- [`{identifier}`](api/{doc_rel_path.name})")

with mkdocs_gen_files.open("reference/index.md", "w") as fd:
    fd.write("\n".join(overview_lines) + "\n")
