"""Targets for one Node line."""

load("//bazel:node_build.bzl", "node_build")

def node_line(major, version, old_v8):
    """Defines the stock control binary and the rootbeer binary for one line.

    Args:
      major: The major version, for example 22.
      version: The pinned version, for example "22.23.4".
      old_v8: True for the lines whose V8 needs the older Clang flags.
    """
    native.alias(
        name = "stock_%d" % major,
        actual = select({
            "//bazel:macos_arm64": "@node_versions//:stock_%d_darwin_arm64" % major,
            "//bazel:linux_x64": "@node_versions//:stock_%d_linux_x64" % major,
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
        source = "@node_versions//:source_%d" % major,
        configure = "@node_versions//:configure_%d" % major,
        old_v8 = old_v8,
        llvm = "//bazel:llvm",
        clang = "//bazel:clang",
        ninja = "//bazel:ninja",
        sysroot_info = "//bazel:sysroot_info",
        sysroot_files = ["//bazel:sysroot_files"],
        # Docker: the default Docker Desktop VM has 8 GB, and V8 compiles use about 1.5 GB each.
        # Remote: the runner has 6 CPUs and 8 GiB. Node 26 peaked at 6.31 GiB with 6 jobs.
        # With 5 jobs, Node 26 does not finish in the 1800 s scheduler limit.
        jobs = select({
            "//bazel:macos_arm64": 0,
            "//bazel:linux_x64": 5,
            "//bazel:linux_x64_remote": 6,
        }),
    )

    native.filegroup(
        name = "dist_%d" % major,
        srcs = [":rootbeer_%d" % major],
        output_group = "dist",
    )
