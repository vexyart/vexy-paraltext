# this_file: scripts/release_artifacts.py
"""Reject private material and inspect the actual archives before upload."""

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

import tomllib

PRIVATE_DIRS = {
    "private",
    "_private",
    ".private",
    "nonpublic",
    "non-public",
    "testdata",
    "ebook-font-l10n",
    ".git",
    ".omc",
    ".swarm",
    ".codegraph",
    ".understand-anything",
    ".specstory",
    ".claude",
    ".venv",
    "__pycache__",
}
PRIVATE_SUFFIXES = {
    ".tmx",
    ".pdf",
    ".epub",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".gguf",
    ".safetensors",
    ".onnx",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".pyc",
    ".log",
}


def private_path(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(
        PRIVATE_DIRS.intersection(path.parts)
        or path.suffix.lower() in PRIVATE_SUFFIXES
        or path.name
        in {
            ".DS_Store",
            "llms.txt",
            ".local-sources.toml",
            "uv.toml",
            ".netrc",
            ".pypirc",
        }
        or path.name.endswith(
            ("-llms.txt", ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")
        )
        or (
            path.name.startswith(".env")
            and path.name not in {".env.example", ".env.sample"}
        )
    )


def check_artifact(path: Path, version: str) -> None:
    """Validate member names, links and package metadata, without extracting."""
    metadata = []
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            files = {m.filename for m in archive.infolist() if not m.is_dir()}
            metadata = [
                (n, archive.read(n)) for n in names if n.endswith(".dist-info/METADATA")
            ]
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
            files = {m.name for m in archive.getmembers() if m.isfile()}
            for member in archive.getmembers():
                if member.issym() or member.islnk():
                    raise ValueError(f"Unexpected archive link: {member.name}")
                if member.name.endswith("/PKG-INFO"):
                    metadata.append((member.name, archive.extractfile(member).read()))
                if (
                    path.suffix == ".crate"
                    and member.name.count("/") == 1
                    and member.name.endswith("/Cargo.toml")
                ):
                    cargo = tomllib.loads(archive.extractfile(member).read().decode())
                    if cargo["package"]["version"] != version:
                        raise ValueError(
                            f"Cargo version does not equal {version}: {path.name}"
                        )
    forbidden = [
        n
        for n in names
        if private_path(n) or ".." in PurePosixPath(n).parts or n.startswith("/")
    ]
    if forbidden:
        raise ValueError(f"Private/unsafe archive members: {forbidden}")
    if path.suffix != ".crate" and not path.name.startswith("site-"):
        if (
            len(metadata) != 1
            or BytesParser().parsebytes(metadata[0][1]).get("Version") != version
        ):
            raise ValueError(f"Artifact version does not equal {version}: {path.name}")
        metadata_name, content = metadata[0]
        headers = BytesParser().parsebytes(content)
        metadata_version = tuple(
            map(int, headers.get("Metadata-Version", "0").split("."))
        )
        if metadata_version >= (2, 4):
            base = PurePosixPath(metadata_name).parent
            if path.suffix == ".whl":
                base /= "licenses"
            for license_file in headers.get_all("License-File", []):
                relative = PurePosixPath(license_file)
                if (
                    not license_file
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or "\\" in license_file
                    or str(base / relative) not in files
                ):
                    raise ValueError(
                        f"License-File {license_file!r} missing or unsafe in {path.name}: "
                        f"expected {base / relative}"
                    )


def record_artifacts(directory: Path, version: str, commit: str) -> list[Path]:
    paths = sorted(
        p
        for p in directory.iterdir()
        if p.is_file()
        and (p.suffix in {".whl", ".crate"} or p.name.endswith(".tar.gz"))
    )
    if not paths:
        raise ValueError("Build produced no artifacts")
    for path in paths:
        check_artifact(path, version)
    data = {
        "version": version,
        "commit": commit,
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    }
    (directory / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
    return paths


def verified_artifacts(directory: Path, version: str, commit: str) -> list[Path]:
    data = json.loads((directory / "manifest.json").read_text())
    if data["version"] != version or data["commit"] != commit:
        raise ValueError("Saved release belongs to a different tag/commit")
    paths = [directory / name for name in data["files"]]
    for path in paths:
        if (
            path.name not in data["files"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != data["files"][path.name]
        ):
            raise ValueError(f"Release artifact changed: {path.name}")
        check_artifact(path, version)
    return paths
