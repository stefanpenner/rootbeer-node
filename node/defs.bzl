"""Targets for one Node line."""

def node_line(major):
    """Defines the stock control binary and the rootbeer binary for one line.

    Args:
      major: The major version, for example 22.
    """
    native.alias(
        name = "stock_%d" % major,
        actual = select({
            "//bazel:macos_arm64": "@stock_%d_darwin_arm64//:bin/node" % major,
            "//bazel:linux_x64": "@stock_%d_linux_x64//:bin/node" % major,
        }),
    )

    # RED: this alias points at stock until the patched build exists.
    native.alias(
        name = "rootbeer_%d" % major,
        actual = ":stock_%d" % major,
    )
