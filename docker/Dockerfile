# Linux x86_64 host for Bazel. The build itself uses the pinned toolchain from
# MODULE.bazel. This image supplies Bazel, POSIX tools, and the host trust store.
FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3

ADD --checksum=sha256:857bed5d2756b4d998d3caebf2d941d13d434c4eda4b1d6d7dda205736c25a93 \
    --chmod=755 \
    https://github.com/bazelbuild/bazel/releases/download/9.1.1/bazel-9.1.1-linux-x86_64 \
    /usr/local/bin/bazel

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 libxml2 libzstd1 zlib1g \
    && rm -rf /var/lib/apt/lists/*

# rules_python refuses to run its interpreter setup as root.
RUN useradd --create-home --uid 1000 builder \
    && mkdir -p /cache && chown builder /cache
USER builder
WORKDIR /src
