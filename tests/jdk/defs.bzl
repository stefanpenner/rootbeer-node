"""Test suites for one JDK line."""

load("@rules_python//python:py_test.bzl", "py_test")

def jdk_tests(line):
    """Defines the hermetic, teeth, and network tests for one JDK line.

    Args:
      line: The feature release, for example "25".
    """
    ours = "//jdk:rootbeerz_%s" % line
    stock_files = "//jdk:stock_%s_files" % line
    stock_java = "//jdk:stock_%s_java" % line
    data = [
        ours,
        stock_files,
        stock_java,
        "Probe.java",
        "//tests:fixtures/emsign-roots.pem",
        "//tests:fixtures/testonly-ca.pem",
        "//tests:fixtures/testonly-leaf.pem",
        "//tests:fixtures/testonly-leaf.key",
        "//trust:mozilla-no-emsign.pem",
    ]
    env = {
        "ROOTBEERZ_JDK": "$(rootpath %s)" % ours,
        "STOCK_JDK": "$(rootpath %s)" % stock_java,
        "PROBE_JAVA": "$(rootpath Probe.java)",
        "EMSIGN_STORE": "$(rootpath //tests:fixtures/emsign-roots.pem)",
        "PINNED_STORE": "$(rootpath //trust:mozilla-no-emsign.pem)",
        "TEST_CA": "$(rootpath //tests:fixtures/testonly-ca.pem)",
        "TEST_LEAF": "$(rootpath //tests:fixtures/testonly-leaf.pem)",
        "TEST_LEAF_KEY": "$(rootpath //tests:fixtures/testonly-leaf.key)",
    }

    py_test(
        name = "hermetic_%s_test" % line,
        srcs = ["hermetic_test.py"],
        main = "hermetic_test.py",
        deps = [":jdklib"],
        data = data,
        env = env,
        size = "medium",
    )

    py_test(
        name = "teeth_%s_test" % line,
        srcs = ["teeth_test.py", "hermetic_test.py"],
        main = "teeth_test.py",
        deps = [":jdklib", "//tests:trustlib"],
        data = data,
        env = env,
        size = "medium",
    )

    py_test(
        name = "network_%s_test" % line,
        srcs = ["network_test.py"],
        main = "network_test.py",
        deps = [":jdklib"],
        data = data,
        env = env,
        size = "large",
        tags = ["requires-network", "no-remote", "no-cache", "external"],
    )
