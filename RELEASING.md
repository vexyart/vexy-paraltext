---
this_file: RELEASING.md
---
# Releasing vexy-paraltext

```bash
./test.sh                    # Tests; failures stop the command
./build.sh                   # Local build, with no formatting/source rewrites
./publish.sh --dry-run       # Tests + next-version artifacts in a disposable Git copy
./publish.sh                 # Commit changes, tag next patch, build, push, publish
./publish.sh --bump minor    # Or --bump major
./publish.sh --resume vX.Y.Z # Retry an existing release at a clean tagged HEAD
```

`publish.sh` includes **all non-ignored working-tree changes** in the release
commit. Review `git diff` and `git status` first. It requires an attached branch,
an `origin` remote (or `--remote NAME`), Git author configuration, uv, and Python
3.12 (uv can provide it). It fetches tags and stops if the remote branch contains
changes absent locally; integrate those changes before retrying.

`gitnextver` supplies the next semantic version from `vMAJOR.MINOR.PATCH` tags.
The wrapper controls commits and pushes itself so tests, archive checks, and
remote-ref verification cannot be bypassed by gitnextver's push behaviour.
The default is a patch increment; minor/major increments reset lower components.

A dry run uses local tags, changes no source-repo commits/tags/remotes, and makes
no registry/site upload. Tests may install dependencies and regenerate ignored
build files. Preview artifacts live in `dist/preview/vX.Y.Z/`.
Release artifacts live in `dist/releases/vX.Y.Z/`; their manifest records the
commit, version and SHA-256 hashes. Uploads use only these verified files.

A failed push/upload may leave a local release tag. Use `--resume` with that tag:
artifacts are hash-checked and reused, and already-published identical files are
accepted. If code changes are required, create a new version instead of moving a
published tag. A failed test creates no tag. A changed working tree during tests
also stops the release.

`PUBLISH_SKIP_UPLOAD=1` skips package/site uploads **but still commits, tags and
pushes**. Use `--dry-run` for a preview without those side effects.

## Python distribution

Hatch VCS derives package metadata and the generated version module from Git.
Generated versions are never committed. For PyPI, set `UV_PUBLISH_TOKEN` in your
shell or use uv's supported credential storage/trusted publishing; do not write
tokens in repository files. `uv publish` uploads the wheel and source archive.


## Private files and standalone clones

Corpora, TMX/PDF/EPUB inputs, databases, model weights, credentials, local configs,
agent state and generated version modules are ignored. Build inputs are explicitly
listed; the release gate rejects private filenames inside actual archives.
Public tests create synthetic fixtures in temporary directories. Never force-add
private data. Ignoring/untracking does not remove files from historical commits.

Local dependency paths belong in editable developer installs, not package metadata.
A private `.local-sources.toml` may record workstation paths; it is reference data,
not an automatically loaded uv config. Release builds use `uv build --no-sources`.
The Python/TM tests use sibling source checkouts when present, otherwise released
packages. Release native Uubed, then Python Uubed, before either consumer.

CI runs tests/builds and retains artifacts. It does not tag or upload packages;
`publish.sh` is the sole publishing path. Each clone includes its own release
helpers. Their canonical copy is in `twardoch/uubed/scripts/`; maintainers sync
copies with `python scripts/sync_release_tools.py /path/to/uubed-project` there.

Versioning/build references: [Hatch VCS](https://github.com/ofek/hatch-vcs),
[Cargo workspace metadata](https://doc.rust-lang.org/cargo/reference/workspaces.html),
[uv publishing](https://docs.astral.sh/uv/guides/package/).
