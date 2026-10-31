"""Finds the macOS SDK on the host. The SDK license does not allow a pinned copy.

The SDK is a host input. The repository records its path, version, and settings
digest in info.json. The build action reads info.json, so a new SDK makes a new
cache key. docs/HERMETICITY.md describes this gap.
"""

_SDK_ROOTS = [
    "/Library/Developer/CommandLineTools/SDKs",
    "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs",
]

# ld64.lld from LLVM 19 cannot read a .tbd file that lists this architecture.
_UNREADABLE_ARCH = "arm64e.x1"

def _version_of(name):
    return name[len("MacOSX"):-len(".sdk")]

def _version_key(name):
    return [int(part) for part in _version_of(name).split(".")]

def _candidates(rctx):
    found = []
    for root in _SDK_ROOTS:
        root_path = rctx.path(root)
        if not root_path.exists:
            continue
        for entry in root_path.readdir():
            name = entry.basename
            if name.startswith("MacOSX") and name.endswith(".sdk") and name != "MacOSX.sdk":
                found.append(entry)
    return sorted(found, key = lambda entry: _version_key(entry.basename), reverse = True)

def _readable_by_lld(rctx, sdk):
    tbd = sdk.get_child("usr").get_child("lib").get_child("libSystem.B.tbd")
    return tbd.exists and _UNREADABLE_ARCH not in rctx.read(tbd)

def _select_sdk(rctx):
    override = rctx.os.environ.get("ROOTBEER_MACOS_SDK")
    if override:
        return rctx.path(override)
    for sdk in _candidates(rctx):
        if _readable_by_lld(rctx, sdk):
            return sdk
    fail("No macOS SDK that ld64.lld can read. Install Command Line Tools, or set ROOTBEER_MACOS_SDK.")

def _sha256(rctx, path):
    result = rctx.execute(["/usr/bin/shasum", "-a", "256", str(path)])
    if result.return_code != 0:
        fail("Cannot hash %s: %s" % (path, result.stderr))
    return result.stdout.split(" ")[0]

def _macos_sdk_impl(rctx):
    if rctx.os.name != "mac os x":
        info = {"path": "", "version": "", "settings_sha256": ""}
    else:
        sdk = _select_sdk(rctx)
        real = sdk.realpath
        settings = real.get_child("SDKSettings.json")
        if not settings.exists:
            fail("%s has no SDKSettings.json" % real)
        settings_data = json.decode(rctx.read(settings))
        info = {
            "path": str(real),
            "version": settings_data["Version"],
            "settings_sha256": _sha256(rctx, settings),
        }
    rctx.file("info.json", json.encode_indent(info, indent = "  ") + "\n")
    rctx.file("BUILD.bazel", 'exports_files(["info.json"])\n')

macos_sdk = repository_rule(
    implementation = _macos_sdk_impl,
    environ = ["ROOTBEER_MACOS_SDK"],
    local = True,
)
