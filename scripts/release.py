#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["gitnextver==1.0.1", "tomlkit>=0.13,<1"]
# ///
# this_file: scripts/release.py
"""Tag, verify and publish one repository. Vendored from twardoch/uubed."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_artifacts import private_path, record_artifacts, verified_artifacts


def run(root: Path, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def public_files(root: Path) -> list[str]:
    files = run(
        root,
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        capture=True,
    ).split("\0")
    files = sorted({f for f in files if f and (root / f).exists()})
    forbidden = [f for f in files if private_path(f)]
    for name in files:
        path = root / name
        if not path.is_symlink():
            continue
        target = path.resolve()
        if not target.is_relative_to(root.resolve()) or private_path(
            str(target.relative_to(root.resolve()))
        ):
            forbidden.append(name)
    if forbidden:
        raise ValueError(f"Untrack private files before releasing: {forbidden}")
    return files


def fingerprint(root: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in public_files(root)
    }


def snapshot(source: Path, target: Path) -> None:
    files = public_files(source)
    run(source, "git", "clone", "--quiet", "--no-hardlinks", str(source), str(target))
    run(target, "git", "remote", "remove", "origin")
    for path in target.iterdir():
        if path.name == ".git":
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    for name in files:
        original, copied = source / name, target / name
        if original.is_symlink() and not original.resolve().is_relative_to(
            source.resolve()
        ):
            raise ValueError(f"External symlink cannot be released: {name}")
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, copied, follow_symlinks=False)
    run(target, "git", "config", "user.name", "Release preview")
    run(target, "git", "config", "user.email", "release@example.invalid")
    run(target, "git", "config", "core.hooksPath", "/dev/null")


def sync_cargo(root: Path, version: str) -> None:
    import tomlkit

    manifest = root / "Cargo.toml"
    document = tomlkit.parse(manifest.read_text())
    document["workspace"]["package"]["version"] = version
    manifest.write_text(tomlkit.dumps(document))
    for member in document["workspace"]["members"]:
        path = root / member / "Cargo.toml"
        data = tomlkit.parse(path.read_text())
        for dependency in data.get("dependencies", {}).values():
            if isinstance(dependency, dict) and "path" in dependency:
                dependency["version"] = version
        path.write_text(tomlkit.dumps(data))
    run(root, "cargo", "metadata", "--format-version", "1", capture=True)


def next_tag(root: Path, bump: str) -> str:
    from git import Repo
    from gitnextver.cli import calculate_next_version, get_last_version_tag

    last = get_last_version_tag(Repo(root))
    if not last or bump == "patch":
        return calculate_next_version(last)
    major, minor, _ = map(int, last[1:].split("."))
    return f"v{major + 1}.0.0" if bump == "major" else f"v{major}.{minor + 1}.0"


def make_tag(root: Path, tag: str, kind: str) -> None:
    public_files(root)
    if kind == "rust":
        sync_cargo(root, tag[1:])
    run(root, "git", "add", "--all")
    if run(root, "git", "status", "--porcelain", capture=True):
        run(root, "git", "commit", "-m", f"Release {tag}")
    run(root, "git", "tag", tag)


def build(root: Path, out: Path, kind: str, tag: str) -> None:
    out.mkdir(parents=True)
    if kind == "docs":
        run(root, "bash", "build.sh")
        with tarfile.open(out / f"site-{tag[1:]}.tar.gz", "w:gz") as archive:
            archive.add(root / "site", arcname="site")
        return
    if kind == "rust":
        run(
            root,
            "uvx",
            "maturin",
            "build",
            "--release",
            "--out",
            str(out),
            "--interpreter",
            "python3.12",
        )
        run(root, "uvx", "maturin", "sdist", "--out", str(out))
        for crate in ("uubed-core", "uubed-tm"):
            run(root, "cargo", "package", "-p", crate, "--locked", "--allow-dirty")
            shutil.copy2(root / "target/package" / f"{crate}-{tag[1:]}.crate", out)
        return
    run(root, "uv", "build", "--no-sources", "--out-dir", str(out))


def push(root: Path, remote: str, branch: str, tag: str) -> None:
    run(
        root,
        "git",
        "push",
        "--atomic",
        remote,
        f"HEAD:refs/heads/{branch}",
        f"refs/tags/{tag}",
    )
    expected = run(root, "git", "rev-parse", "HEAD", capture=True)
    refs = run(
        root,
        "git",
        "ls-remote",
        remote,
        f"refs/heads/{branch}",
        f"refs/tags/{tag}*",
        capture=True,
    ).splitlines()
    found = {line.split()[1]: line.split()[0] for line in refs}
    actual_tag = found.get(f"refs/tags/{tag}^{{}}", found.get(f"refs/tags/{tag}"))
    if found.get(f"refs/heads/{branch}") != expected or actual_tag != expected:
        raise ValueError("Remote branch/tag verification failed; nothing uploaded")


def upload(root: Path, paths: list[Path], kind: str, tag: str, remote: str) -> None:
    if os.environ.get("PUBLISH_SKIP_UPLOAD") == "1":
        print("Package/site upload skipped; Git branch and tag HAVE been pushed.")
        return
    if kind == "docs":
        with tempfile.TemporaryDirectory(prefix="uubed-site-") as temporary:
            with tarfile.open(paths[0]) as archive:
                archive.extractall(temporary, filter="data")
            run(
                root,
                "uvx",
                "--from",
                "ghp-import==2.1.0",
                "ghp-import",
                "-n",
                "-p",
                "-r",
                remote,
                "-b",
                "gh-pages",
                "-m",
                f"Deploy {tag}",
                str(Path(temporary) / "site"),
            )
        expected = run(root, "git", "rev-parse", "gh-pages", capture=True)
        actual = run(
            root, "git", "ls-remote", remote, "refs/heads/gh-pages", capture=True
        )
        if not actual or actual.split()[0] != expected:
            raise ValueError("Published site branch verification failed")
        return
    if kind == "rust":
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        for crate in ("uubed-core", "uubed-tm"):
            request = Request(
                f"https://crates.io/api/v1/crates/{crate}/{tag[1:]}",
                headers={"User-Agent": "uubed-release"},
            )
            try:
                with urlopen(request, timeout=30) as response:
                    published = json.load(response)
                import hashlib

                artifact = next(
                    p for p in paths if p.name == f"{crate}-{tag[1:]}.crate"
                )
                if (
                    published["version"]["checksum"]
                    != hashlib.sha256(artifact.read_bytes()).hexdigest()
                ):
                    raise ValueError(
                        f"Published crate differs: {crate}; use a new version"
                    )
            except HTTPError as error:
                if error.code != 404:
                    raise
                run(root, "cargo", "publish", "-p", crate, "--locked")
    distributions = [
        str(p) for p in paths if p.suffix == ".whl" or p.name.endswith(".tar.gz")
    ]
    run(root, "uv", "publish", *distributions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test and build a tagged disposable copy; no commits, tags, pushes or uploads in the source repo",
    )
    parser.add_argument(
        "--resume",
        metavar="TAG",
        help="Retry the exact clean tagged HEAD, reusing verified artifacts",
    )
    parser.add_argument("--bump", choices=["patch", "minor", "major"], default="patch")
    parser.add_argument("--remote", default="origin")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    config = json.loads((root / "release.json").read_text())
    kind = config["kind"]
    if (
        Path(run(root, "git", "rev-parse", "--show-toplevel", capture=True)).resolve()
        != root
    ):
        raise ValueError("Run publish.sh at its repository root")
    public_files(root)
    if args.resume and (
        not re.fullmatch(r"v\d+\.\d+\.\d+", args.resume)
        or run(root, "git", "status", "--porcelain", capture=True)
        or run(root, "git", "rev-parse", f"{args.resume}^{{commit}}", capture=True)
        != run(root, "git", "rev-parse", "HEAD", capture=True)
    ):
        raise ValueError("--resume requires a clean checkout at the exact release tag")
    branch = run(root, "git", "symbolic-ref", "--short", "HEAD", capture=True)
    if not args.dry_run:
        run(root, "git", "fetch", "--tags", args.remote)
        remote_branch = run(
            root, "git", "ls-remote", "--heads", args.remote, branch, capture=True
        )
        if remote_branch:
            run(
                root,
                "git",
                "merge-base",
                "--is-ancestor",
                remote_branch.split()[0],
                "HEAD",
            )
    tag = args.resume or next_tag(root, args.bump)
    print(
        f"{config['name']}: {'preview' if args.dry_run else 'release'} {tag}",
        flush=True,
    )
    tested_source = fingerprint(root)
    run(root, "bash", "test.sh")
    if fingerprint(root) != tested_source:
        raise ValueError(
            "Source changed during tests; rerun against the finished changes"
        )
    with tempfile.TemporaryDirectory(prefix="uubed-release-") as temporary:
        checkout = root
        if args.dry_run:
            checkout = Path(temporary) / "source"
            snapshot(root, checkout)
        if not args.resume:
            make_tag(checkout, tag, kind)
        commit = run(checkout, "git", "rev-parse", "HEAD", capture=True)
        destination = root / "dist" / ("preview" if args.dry_run else "releases") / tag
        if args.resume and (destination / "manifest.json").exists():
            paths = verified_artifacts(destination, tag[1:], commit)
        else:
            fresh = Path(temporary) / "artifacts"
            build(checkout, fresh, kind, tag)
            record_artifacts(fresh, tag[1:], commit)
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(fresh, destination)
            paths = verified_artifacts(destination, tag[1:], commit)
        if not args.dry_run:
            public_files(root)
            if run(root, "git", "status", "--porcelain", capture=True):
                raise ValueError(
                    f"Build changed tracked files; inspect changes before --resume {tag}"
                )
            push(root, args.remote, branch, tag)
            upload(root, paths, kind, tag, args.remote)
        print(f"Verified {tag}: {destination}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"Release stopped: {error}")
