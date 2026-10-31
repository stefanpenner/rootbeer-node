"""Test suites for one Node line."""

load("@rules_python//python:py_test.bzl", "py_test")

PINNED_STORE_SHA256 = "f41ef11ed4909cbd21e651383b76298bf83d7b42a022f48d1d19dd8d4b986901"

def rootbeer_tests(major, version):
    """Defines the hermetic and the network test for one Node line.

    Args:
      major: The major version, for example 22.
      version: The pinned version, for example "22.23.4".
    """
    node = "//node:rootbeer_%d" % major
    stock = "//node:stock_%d" % major
    common_data = [
        node,
        stock,
        "//trust:mozilla-no-emsign.pem",
        "fixtures/emsign-roots.pem",
        "fixtures/empty.pem",
    ]
    common_env = {
        "ROOTBEER_NODE": "$(rootpath %s)" % node,
        "STOCK_NODE": "$(rootpath %s)" % stock,
        "NODE_VERSION": version,
        "EMPTY_STORE": "$(rootpath fixtures/empty.pem)",
        "PINNED_STORE": "$(rootpath //trust:mozilla-no-emsign.pem)",
        "EMSIGN_STORE": "$(rootpath fixtures/emsign-roots.pem)",
    }

    source = "@node_%d//:" % major
    py_test(
        name = "source_%d_test" % major,
        srcs = ["source/patch_test.py"],
        main = "source/patch_test.py",
        deps = [":trustlib"],
        data = [
            source + "src/node_root_certs.h",
            source + "src/crypto/crypto_context.cc",
            source + "src/node_options.cc",
            source + "deps/openssl/openssl_common.gypi",
        ],
        env = {
            "ROOT_CERTS_H": "$(rootpath %ssrc/node_root_certs.h)" % source,
            "CRYPTO_CONTEXT_CC": "$(rootpath %ssrc/crypto/crypto_context.cc)" % source,
            "NODE_OPTIONS_CC": "$(rootpath %ssrc/node_options.cc)" % source,
            "OPENSSL_COMMON_GYPI": "$(rootpath %sdeps/openssl/openssl_common.gypi)" % source,
        },
        size = "small",
    )

    py_test(
        name = "hermetic_%d_test" % major,
        srcs = ["hermetic_test.py"],
        main = "hermetic_test.py",
        deps = [":trustlib"],
        data = common_data + [
            "loopback.js",
            "fixtures/testonly-ca.pem",
            "fixtures/testonly-leaf.pem",
            "fixtures/testonly-leaf.key",
        ],
        env = common_env | {
            "LOOPBACK_JS": "$(rootpath loopback.js)",
            "TEST_CA": "$(rootpath fixtures/testonly-ca.pem)",
            "TEST_CA_SUBJECT_HASH": TEST_CA_SUBJECT_HASH,
            "TEST_LEAF": "$(rootpath fixtures/testonly-leaf.pem)",
            "TEST_LEAF_KEY": "$(rootpath fixtures/testonly-leaf.key)",
            "PINNED_STORE_SHA256": PINNED_STORE_SHA256,
        },
        size = "medium",
    )

    py_test(
        name = "network_%d_test" % major,
        srcs = ["network_test.py"],
        main = "network_test.py",
        deps = [":trustlib"],
        data = common_data + ["probe.js"],
        env = common_env | {"PROBE_JS": "$(rootpath probe.js)"},
        size = "large",
        tags = ["requires-network", "no-remote", "no-cache", "external"],
    )

# The OpenSSL subject hash of tests/fixtures/testonly-ca.pem.
TEST_CA_SUBJECT_HASH = "c366c54f"
