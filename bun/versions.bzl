"""Fetches Bun inputs with a pinned sha256. Version and source sha256 come from runtimes/bun.json."""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive", "http_file")
load("//bun:pins.bzl", "STOCK")

_RELEASE = "https://github.com/oven-sh/bun/releases/download/bun-v{version}/{name}.zip"
_SOURCE = "https://github.com/oven-sh/bun/archive/refs/tags/bun-v{version}.tar.gz"

_SOURCE_BUILD = """
package(default_visibility = ["//visibility:public"])

exports_files(["package.json"])

# A deleted file is absent here, so the source test can see the deletion.
filegroup(
    name = "root_sources",
    srcs = glob(
        [
            "packages/bun-usockets/certdata.txt",
            "packages/bun-usockets/root_certs.*",
            "packages/bun-usockets/src/crypto/root_certs.cpp",
            "src/js/node/tls.ts",
            "src/runtime/socket/bundled_root_certs.rs",
        ],
        allow_empty = True,
    ),
)
"""

_STOCK_BUILD = """
package(default_visibility = ["//visibility:public"])

exports_files(["bun"])
"""

# Files that hold the Mozilla roots. The build does not read the last two, but a tree with no roots
# must not hold them.
_REMOVED = [
    "packages/bun-usockets/root_certs.der",
    "packages/bun-usockets/root_certs.txt",
    "packages/bun-usockets/certdata.txt",
]

def _patched_source_impl(rctx):
    rctx.download_and_extract(
        url = rctx.attr.url,
        sha256 = rctx.attr.sha256,
        stripPrefix = rctx.attr.strip_prefix,
    )
    rctx.patch(rctx.attr.patch, strip = 1)
    for path in _REMOVED:
        rctx.delete(path)
    rctx.file("BUILD.bazel", _SOURCE_BUILD)

_patched_source = repository_rule(
    implementation = _patched_source_impl,
    attrs = {
        "patch": attr.label(mandatory = True),
        "sha256": attr.string(mandatory = True),
        "strip_prefix": attr.string(mandatory = True),
        "url": attr.string(mandatory = True),
    },
)

def _bun_impl(mctx):
    manifest = json.decode(mctx.read(Label("//runtimes:bun.json")))
    for entry in manifest["versions"]:
        line = entry["line"]
        version = entry["version"]
        prefix = "bun_%s_" % line
        http_file(
            name = prefix + "tarball",
            url = _SOURCE.format(version = version),
            sha256 = entry["sha256"],
            downloaded_file_path = "bun.tar.gz",
        )
        _patched_source(
            name = prefix + "src",
            url = _SOURCE.format(version = version),
            sha256 = entry["sha256"],
            strip_prefix = "bun-bun-v%s" % version,
            patch = Label("//bun:patches/0001-system-store-only.patch"),
        )
        http_archive(
            name = prefix + "stock_darwin_arm64",
            url = _RELEASE.format(version = version, name = "bun-darwin-aarch64"),
            sha256 = STOCK[line]["darwin_arm64"],
            strip_prefix = "bun-darwin-aarch64",
            build_file_content = _STOCK_BUILD,
        )
        http_archive(
            name = prefix + "stock_linux_x64",
            url = _RELEASE.format(version = version, name = "bun-linux-x64"),
            sha256 = STOCK[line]["linux_x64"],
            strip_prefix = "bun-linux-x64",
            build_file_content = _STOCK_BUILD,
        )
    return mctx.extension_metadata(reproducible = True)

bun = module_extension(implementation = _bun_impl)
