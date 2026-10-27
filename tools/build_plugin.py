"""Build the plugin zip for plugins.qgis.org and check it before upload.

Usage (repository root):  python3 tools/build_plugin.py
Writes dist/fao56_cwr_mapper-<version>.zip and exits with status 1 if any
check fails. Checks follow the PyQGIS developer cookbook (Releasing your
plugin; metadata.txt): required metadata fields, LICENSE file, folder name,
icon, no generated or hidden files. The upload itself remains the final check.
"""

import configparser
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = "fao56_cwr_mapper"
SRC = os.path.join(ROOT, PACKAGE)
DIST = os.path.join(ROOT, "dist")

REQUIRED = ("name", "qgisMinimumVersion", "description", "about", "version", "author", "email",
            "repository")
RECOMMENDED = ("tracker", "homepage", "icon", "tags", "category", "changelog")
CATEGORIES = ("Raster", "Vector", "Database", "Mesh", "Web")
VAGUE_TAGS = {"vector", "raster", "plugin", "qgis", "python"}
SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".orig", ".rej")


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def read_metadata(rep):
    path = os.path.join(SRC, "metadata.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except UnicodeDecodeError:
        rep.error("metadata.txt is not UTF-8")
        return {}
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str                  # keep camelCase keys
    cfg.read_string(text)
    if not cfg.has_section("general"):
        rep.error("metadata.txt has no [general] section")
        return {}
    return dict(cfg.items("general"))


def check_metadata(md, rep):
    for key in REQUIRED:
        if not md.get(key, "").strip():
            rep.error("metadata: required field '{}' is missing or empty".format(key))
    for key in RECOMMENDED:
        if not md.get(key, "").strip():
            rep.warn("metadata: recommended field '{}' is empty".format(key))
    if not re.match(r"^\d+(\.\d+)+$", md.get("version", "")):
        rep.error("metadata: version '{}' is not dotted notation".format(md.get("version")))
    if not re.match(r"^\d+\.\d+(\.\d+)?$", md.get("qgisMinimumVersion", "")):
        rep.error("metadata: qgisMinimumVersion '{}' is not like 3.22".format(md.get("qgisMinimumVersion")))
    for key in ("experimental", "deprecated"):
        if key in md and md[key] not in ("True", "False"):
            rep.error("metadata: {} must be True or False, not '{}'".format(key, md[key]))
    if "\n" in md.get("description", ""):
        rep.error("metadata: description must be a single line")
    for key in ("description", "about"):
        if re.search(r"<[a-zA-Z/][^>]*>", md.get(key, "")):
            rep.error("metadata: {} must not contain HTML".format(key))
    if md.get("category") and md["category"] not in CATEGORIES:
        rep.error("metadata: category '{}' must be one of {}".format(md["category"], ", ".join(CATEGORIES)))
    for key in ("repository", "tracker", "homepage"):
        if md.get(key) and not md[key].startswith(("http://", "https://")):
            rep.error("metadata: {} is not a URL".format(key))
    tags = [t.strip().lower() for t in md.get("tags", "").split(",") if t.strip()]
    vague = sorted(set(tags) & VAGUE_TAGS)
    if vague:
        rep.warn("metadata: uninformative tags {}".format(vague))
    icon = md.get("icon", "")
    if icon:
        if not icon.lower().endswith((".png", ".jpg", ".jpeg")):
            rep.error("metadata: icon must be PNG or JPEG")
        elif not os.path.isfile(os.path.join(SRC, icon)):
            rep.error("metadata: icon file '{}' not found in the package".format(icon))


def collect_files(rep):
    files = []
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, SRC)
            if name in SKIP_FILES or name.endswith(SKIP_SUFFIXES) or name.startswith("."):
                continue
            if os.path.islink(full):
                rep.error("symbolic link in package: " + rel)
                continue
            files.append((full, rel))
    return files


def check_package(files, rep):
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", PACKAGE):
        rep.error("folder name '{}' must be ASCII letters, digits, _ or - and not start "
                  "with a digit".format(PACKAGE))
    names = {rel for _, rel in files}
    for required in ("metadata.txt", "__init__.py", "LICENSE"):
        if required not in names:
            rep.error("package lacks " + required)
    for _, rel in files:
        base = os.path.basename(rel)
        if re.match(r"^(ui_.*|resources_rc)\.py$", base):
            rep.error("generated file in package: " + rel)
    for full, rel in files:
        if rel.endswith(".py"):
            with open(full, encoding="utf-8") as fh:
                try:
                    compile(fh.read(), rel, "exec")
                except SyntaxError as exc:
                    rep.error("syntax error in {}: {}".format(rel, exc))


def write_zip(files, version):
    os.makedirs(DIST, exist_ok=True)
    path = os.path.join(DIST, "{}-{}.zip".format(PACKAGE, version))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for full, rel in files:
            zf.write(full, "{}/{}".format(PACKAGE, rel.replace(os.sep, "/")))
        readme = os.path.join(ROOT, "README.md")           # recommended in the package
        if os.path.isfile(readme) and "README.md" not in {rel for _, rel in files}:
            zf.write(readme, PACKAGE + "/README.md")
    return path


def check_zip(path, rep):
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = zf.testzip()
    if bad:
        rep.error("corrupt zip entry: " + bad)
    tops = {n.split("/")[0] for n in names}
    if tops != {PACKAGE}:
        rep.error("zip must contain exactly one top-level folder, found {}".format(sorted(tops)))
    for n in names:
        parts = n.split("/")
        if "__MACOSX" in parts or "__pycache__" in parts or any(p.startswith(".") for p in parts):
            rep.error("unwanted entry in zip: " + n)
        if n.endswith(SKIP_SUFFIXES):
            rep.error("compiled file in zip: " + n)
    return names


def main():
    rep = Report()
    md = read_metadata(rep)
    check_metadata(md, rep)
    files = collect_files(rep)
    check_package(files, rep)
    if rep.errors:
        path, names = None, []
    else:
        path = write_zip(files, md["version"])
        names = check_zip(path, rep)
    print("{} {} (QGIS >= {}, experimental={})".format(
        md.get("name", "?"), md.get("version", "?"), md.get("qgisMinimumVersion", "?"),
        md.get("experimental", "?")))
    if path:
        print("zip: {} ({} files, {:.1f} kB)".format(
            os.path.relpath(path, ROOT), len(names), os.path.getsize(path) / 1024))
    for w in rep.warnings:
        print("WARNING: " + w)
    for e in rep.errors:
        print("ERROR: " + e)
    print("OK" if not rep.errors else "FAILED ({} error(s))".format(len(rep.errors)))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
