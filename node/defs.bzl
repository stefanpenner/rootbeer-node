"""Targets for one Node line."""

load("//bazel:node_build.bzl", "node_build")

def node_line(major, version):
    """Defines the stock control binary and the rootbeer binary for one line.

    Args:
      major: The major version, for example 22.
      version: The pinned version, for example "22.23.4".
    """
    native.alias(
        name = "stock_%d" % major,
        actual = select({
            "//bazel:macos_arm64": "@stock_%d_darwin_arm64//:bin/node" % major,
            "//bazel:linux_x64": "@stock_%d_linux_x64//:bin/node" % major,
        }),
    )

    node_build(
        name = "rootbeer_%d" % major,
        version = version,
        os_name = select({
            "//bazel:macos_arm64": "darwin",
            "//bazel:linux_x64": "linux",
        }),
        arch = select({
            "//bazel:macos_arm64": "arm64",
            "//bazel:linux_x64": "x64",
        }),
        source = "@node_%d//:source" % major,
        configure = "@node_%d//:configure.py" % major,
        llvm = "//bazel:llvm",
        clang = "//bazel:clang",
        ninja = "//bazel:ninja",
        sysroot_info = "//bazel:sysroot_info",
        sysroot_files = ["//bazel:sysroot_files"],
        # The default Docker Desktop VM has 8 GB, and V8 compiles use about 1.5 GB each.
        jobs = select({
            "//bazel:macos_arm64": 0,
            "//bazel:linux_x64": 5,
        }),
    )

    native.filegroup(
        name = "dist_%d" % major,
        srcs = [":rootbeer_%d" % major],
        output_group = "dist",
    )
