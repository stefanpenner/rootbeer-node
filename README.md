# rootbeer

Node.js LTS builds with no bundled root certificates. Trust comes from the local store.

Work in progress. This repository builds Node 16, 18, 20, and 22 from pinned source with Bazel.

`tests/fixtures/testonly-leaf.key` is a private key for a test certificate on `localhost`.
The key has no value outside the tests. The test CA key does not exist anymore.
