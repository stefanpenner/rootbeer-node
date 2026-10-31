"""Packs a local macOS SDK into a private tarball and prints its sha256.

The Apple license does not allow a public copy of the SDK. Keep the tarball private.
Do not commit it, upload it, add it to an artifact or a cache, or put it at a public URL.
The tool refuses an output path in a git work tree. docs/HERMETICITY.md has the procedure.

Usage: python3 tools/pack_macos_sdk.py --out ~/private/MacOSX.sdk.tar.gz [--sdk PATH]
"""

import argparse
import gzip
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path

SDK_ROOTS = [
    "/Library/Developer/CommandLineTools/SDKs",
    "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs",
]

# bazel/sdk.bzl has the same value. ld64.lld from LLVM 19 cannot read a .tbd file with this architecture.
UNREADABLE_ARCH = "arm64e.x1"


def readable_by_lld(sdk):
    tbd = sdk / "usr/lib/libSystem.B.tbd"
    return tbd.is_file() and UNREADABLE_ARCH not in tbd.read_text(errors="replace")


def newest_readable_sdk():
    found = []
    for root in map(Path, SDK_ROOTS):
        if root.is_dir():
            found += [path for path in root.glob("MacOSX*.sdk") if path.name != "MacOSX.sdk"]
    version = lambda path: [int(part) for part in path.name[len("MacOSX"):-len(".sdk")].split(".")]
    for sdk in sorted(found, key=version, reverse=True):
        if readable_by_lld(sdk):
            return sdk
    sys.exit("No local SDK that ld64.lld can read. Install Command Line Tools, or give --sdk.")


def check_sdk(sdk):
    if not (sdk / "SDKSettings.json").is_file():
        sys.exit(f"{sdk} has no SDKSettings.json")
    json.loads((sdk / "SDKSettings.json").read_text())
    if not readable_by_lld(sdk):
        sys.exit(f"ld64.lld cannot read {sdk}. Select a different SDK.")


def check_out(out):
    """Refuses an output path in a git work tree, so a later `git add` cannot publish the SDK."""
    for parent in out.parents:
        if (parent / ".git").exists():
            sys.exit(f"Put the tarball outside the git work tree at {parent}.")


def clean(member):
    """Removes the host owner and the time, so the same SDK gives the same bytes."""
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    member.mtime = 0
    return member


def members(sdk):
    yield sdk, sdk.name
    for root, dirs, files in os.walk(sdk):
        dirs.sort()
        rel = Path(root).relative_to(sdk)
        for name in sorted(dirs + files):
            yield Path(root) / name, str(Path(sdk.name) / rel / name)


def write_tarball(sdk, out):
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = out.with_name(out.name + ".partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0) as packed:
            with tarfile.open(fileobj=packed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path, name in members(sdk):
                    archive.add(path, arcname=name, recursive=False, filter=clean)
    os.replace(partial, out)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Packs a local macOS SDK into a private tarball.")
    parser.add_argument("--sdk", type=Path, help="The SDK directory. Default: the newest SDK that ld64.lld can read.")
    parser.add_argument("--out", type=Path, required=True, help="The tarball path, outside any git work tree.")
    args = parser.parse_args()

    out = args.out.expanduser().resolve()
    check_out(out)
    sdk = args.sdk.expanduser().resolve() if args.sdk else newest_readable_sdk().resolve()
    check_sdk(sdk)
    write_tarball(sdk, out)
    digest = sha256_of(out)
    print(f"{digest}  {out}")
    print("Keep this tarball private. Add these lines to ~/.bazelrc:")
    print(f"common:pinned-sdk --repo_env=ROOTBEER_PINNED_SDK_URL={out.as_uri()}")
    print(f"common:pinned-sdk --repo_env=ROOTBEER_PINNED_SDK_SHA256={digest}")


if __name__ == "__main__":
    main()
