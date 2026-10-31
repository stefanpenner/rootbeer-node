# Adding a Node version

A version is one `node.version` tag in `MODULE.bazel`. The module extension in
`bazel/node_versions.bzl` turns each tag into the patched source, the stock control
binaries, the `//node:rootbeer_<major>` target, and the test targets.

## A new release of a line that is already pinned (for example 22.23.4 to 22.24.0)

```
python3 tools/add_node_version.py 22.24.0
bazel test //tests:source_22_test //tests:versions_test
bazel build //node:rootbeer_22 //node:dist_22 --output_groups=+dist
bazel test //tests:hermetic_22_test //tests:network_22_test
```

The tool reads `SHASUMS256.txt` from nodejs.org. It rewrites the tag and the README row.
The patches in `patches/22/` must still apply. `source_22_test` fails when they do not.
In that case run `python3 tools/make_patches.py <dir with node-vX.Y.Z trees> patches`.
It stops when a replacement does not match exactly once, so it never writes a partial patch.

## A new line (for example 24)

```
python3 tools/add_node_version.py 24.22.2
```

The tool edits `MODULE.bazel`, the matrices in `ci.yml`, and the README. It then runs
`tools/make_patches.py --only 24`. That stops with a message when the line has no entry in
`FAMILIES`. A family is the shape of the trust code in `src/crypto/crypto_context.cc`.
Node 16, 18, and 20 share the `legacy` family. Node 22 is `modern`.
Node 24 is a new family. Its `NewRootCertStore`, `GetOrCreateRootCertStore`, and
`tls.setDefaultCACertificates` live in different places, so the existing edits do not match.

For a new family:

1. Write a context function in `tools/make_patches.py`, and add it to `FAMILIES`.
   Keep the semantics of the other families. The bundled list stays empty, and
   `X509_STORE_set_default_paths` runs on every path.
2. Run `python3 tools/add_node_version.py 24.22.2` again.
3. Run the test chain above. The hermetic tests, including the PEM scan, prove that the binary
   holds no roots, and the network tests prove that the eMudhra hosts fail with the pinned store.

Pass `--old-v8` when the V8 of the line needs the Clang warning flags and the libc++ 19 patches
(Node 16 and 18 today). Add `OLD_ZLIB_HEADERS` entries in `make_patches.py` for such a line.

## What the tests check

`tests/versions_test.py` fails when the CI matrix, the README table, the patch files, or
`make_patches.py` disagree with the tags. `tests/add_node_version_test.py` tests the tool.

After a build, record the result in `STATUS.md` and the artifact hashes in the README.
