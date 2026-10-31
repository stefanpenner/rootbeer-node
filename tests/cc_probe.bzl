"""Writes what the resolved C++ toolchain is, for tests/cc_toolchain_test.py to read."""

load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load("@rules_cc//cc:find_cc_toolchain.bzl", "CC_TOOLCHAIN_ATTRS", "find_cc_toolchain", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")

_ACTIONS = [
    ACTION_NAMES.c_compile,
    ACTION_NAMES.cpp_compile,
    ACTION_NAMES.cpp_link_executable,
    ACTION_NAMES.cpp_link_static_library,
]

def _cc_probe_impl(ctx):
    cc_toolchain = find_cc_toolchain(ctx)
    features = cc_common.configure_features(ctx = ctx, cc_toolchain = cc_toolchain)
    out = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(out, json.encode_indent({
        "include_directories": cc_toolchain.built_in_include_directories,
        "tools": {
            action: cc_common.get_tool_for_action(feature_configuration = features, action_name = action)
            for action in _ACTIONS
        },
        "toolchain_id": cc_toolchain.toolchain_id,
    }))
    return [DefaultInfo(files = depset([out]), runfiles = ctx.runfiles([out]))]

cc_probe = rule(
    implementation = _cc_probe_impl,
    attrs = CC_TOOLCHAIN_ATTRS,
    toolchains = use_cc_toolchain(),
    fragments = ["cpp"],
)
