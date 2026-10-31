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

    hermetic_data = [
        "loopback.js",
        "//bazel:readobj",
        "fixtures/testonly-ca.pem",
        "fixtures/testonly-leaf.pem",
        "fixtures/testonly-leaf.key",
    ]
    stock_data = [d for d in common_data if d != node] + hermetic_data
    hermetic_env = common_env | {
        "LOOPBACK_JS": "$(rootpath loopback.js)",
        "READOBJ": "$(rootpath //bazel:readobj)",
        "TEST_CA": "$(rootpath fixtures/testonly-ca.pem)",
        "TEST_CA_SUBJECT_HASH": TEST_CA_SUBJECT_HASH,
        "TEST_LEAF": "$(rootpath fixtures/testonly-leaf.pem)",
        "TEST_LEAF_KEY": "$(rootpath fixtures/testonly-leaf.key)",
        "PINNED_STORE_SHA256": PINNED_STORE_SHA256,
    }

    source = "@node_versions//:"
    source_data = [
        source + "node_root_certs_h_%d" % major,
        source + "crypto_context_cc_%d" % major,
        source + "node_mksnapshot_cc_%d" % major,
        source + "node_options_cc_%d" % major,
        source + "openssl_common_gypi_%d" % major,
        source + "configure_%d" % major,
        "//bazel:build_node.py",
    ]
    source_env = {
        "ROOT_CERTS_H": "$(rootpath %snode_root_certs_h_%d)" % (source, major),
        "CRYPTO_CONTEXT_CC": "$(rootpath %scrypto_context_cc_%d)" % (source, major),
        "NODE_MKSNAPSHOT_CC": "$(rootpath %snode_mksnapshot_cc_%d)" % (source, major),
        "NODE_OPTIONS_CC": "$(rootpath %snode_options_cc_%d)" % (source, major),
        "OPENSSL_COMMON_GYPI": "$(rootpath %sopenssl_common_gypi_%d)" % (source, major),
        "CONFIGURE_PY": "$(rootpath %sconfigure_%d)" % (source, major),
        "BUILD_NODE": "$(rootpath //bazel:build_node.py)",
    }
    py_test(
        name = "source_%d_test" % major,
        srcs = ["source/patch_test.py"],
        main = "source/patch_test.py",
        deps = [":trustlib"],
        data = source_data,
        env = source_env,
        size = "small",
    )

    py_test(
        name = "source_mutation_%d_test" % major,
        srcs = ["source/patch_mutation_test.py", "source/patch_test.py"],
        main = "source/patch_mutation_test.py",
        imports = ["source"],
        deps = [":trustlib"],
        data = source_data + ["//patches:all"],
        env = source_env | {
            "NODE_MAJOR": str(major),
            "PATCHES": "$(rootpaths //patches:all)",
        },
        size = "small",
    )

    # The stock binary is a download, so these checks need no Node build.
    py_test(
        name = "stock_teeth_%d_test" % major,
        srcs = ["stock_teeth_test.py", "hermetic_test.py"],
        main = "stock_teeth_test.py",
        deps = [":trustlib"],
        data = stock_data,
        env = hermetic_env | {"ROOTBEER_NODE": "$(rootpath %s)" % stock},
        size = "medium",
    )

    py_test(
        name = "hermetic_%d_test" % major,
        srcs = ["hermetic_test.py"],
        main = "hermetic_test.py",
        deps = [":trustlib"],
        data = common_data + hermetic_data,
        env = hermetic_env,
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
