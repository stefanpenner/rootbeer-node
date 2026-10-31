# rootbeer-node

> **Why the name.** Root certs are removed. Node is left. So: rootbeer-node. It trusts only the root store on your system.

Node.js 16, 18, 20, 22, 24, and 26 with no bundled root certificates.
Each binary trusts only the local (system) trust store.

Stock Node trusts its own list of roots. Ours trusts what your host trusts.

## Example

Both commands use a store that has no emSign roots.
`testevg1.emsign.com` is an eMudhra test host. Mozilla, Google, and Apple distrust its root.

```sh
export SSL_CERT_FILE=trust/mozilla-no-emsign.pem

# stock Node
node -p 'require("tls").rootCertificates.length'    # 119
node tests/probe.js https://testevg1.emsign.com     # {"trusted":true,"status":302}

# rootbeer-node
./node -p 'require("tls").rootCertificates.length'  # 0
./node tests/probe.js https://testevg1.emsign.com   # {"trusted":false,"code":"UNABLE_TO_GET_ISSUER_CERT_LOCALLY",...}
./node tests/probe.js https://example.com           # {"trusted":true,"status":200}
```

Stock Node ignores your store and trusts emSign.
Our Node uses your store, so it rejects emSign and still trusts valid hosts.

## Why

You cannot remove a root from the list in stock Node.
You must wait for a new Node release.
Here, the host store is the only source of trust.
Remove a root from the host, and the next Node process stops trusting it.

## Trust model

- `tls.rootCertificates` is empty.
- `--use-bundled-ca` has no effect.
- OpenSSL reads the store from `SSL_CERT_FILE`, `SSL_CERT_DIR`, or `/etc/ssl`.
- `NODE_EXTRA_CA_CERTS` still adds roots. This is by design, for now.
- `--use-system-ca` and `NODE_USE_SYSTEM_CA=1` add the system store of the operating system to the local store (Node 24 and 26).
- `tls.getCACertificates('default')` does not show the local store (Node 24 and 26).
  The list can be empty while `SSL_CERT_FILE` gives trust.
- `tls.setDefaultCACertificates()` replaces the store. A program that passes that empty list removes its own trust.
- Anyone who can set these variables or write these paths controls trust.
- A host with no store has no trust. Each TLS connection fails.
- This project does not remove a bad root from your host.
- OpenSSL does not check revocation.

## Versions

`MODULE.bazel` pins each version, one `node.version` tag per line.
Each checksum comes from the release `SHASUMS256.txt`.

| Line | Version | Source sha256 | macOS arm64 | Linux x86_64 |
|---|---|---|---|---|
| 26 | 26.13.0 | `986ead18ef18256831bae3e57d94aef680a7b84cfd4044f3e8471f833fbd7191` | pass | untested |
| 24 | 24.22.2 | `b2f5443a34a38d863e87c0f5f80c03630fc16917dfe16f26c1cec44c0b542959` | untested | untested |
| 22 | 22.23.4 | `4dd79de8cdc85d65cb32f48a75aee1067bf00bf94b96ecc8e4c2f82f6f0272c2` | pass | pass |
| 20 | 20.20.2 | `8cb85a81f75169eb811f7b2512cf17a646826430debbe016a7461f31e286fdef` | pass | pass |
| 18 | 18.20.8 | `ec60a6d2344ef9e1f093991ca1bb6bbe92c61c29d1762c4b99e08f87dbb91e2f` | pass | pass |
| 16 | 16.20.2 | `33188eb11b977113adb65b2e09d71bddd63f12168ba73ceadae6c27938dc9e93` | pass | pass |

"Pass" means the source, hermetic, and network tests passed on a built binary.
"Untested" means that the hermetic and network tests have not run for this pair. The patches apply and the source tests pass.
[STATUS.md](STATUS.md) has the evidence.
Node 16 and 18 are past end of life.
Node 26 has no Temporal API here, because the build declares no Rust toolchain. A stock Node 26 can have it.

To add a version, run `python3 tools/add_node_version.py <version>`.
See [docs/ADDING_A_VERSION.md](docs/ADDING_A_VERSION.md).

## How it works

1. Bazel builds Node from pinned source with a pinned toolchain.
2. Patches empty `src/node_root_certs.h` and force the local store.
3. Tests check that the binary starts and trusts valid hosts.
4. Tests check that it fails against the eMudhra test hosts when the local store has no emSign roots.

`patches/<line>/` holds the patches.
`tools/make_patches.py` makes them from pristine source.

## Build

Install Bazel. Then run:

```sh
bazel build //node:rootbeer_22 //node:dist_22 --output_groups=+dist
```

Change `22` to build another line.
The binary needs macOS 14 or later, or Linux glibc 2.25 or later.

On Linux, you can build in the pinned Docker image:

```sh
docker build --platform linux/amd64 -f docker/Dockerfile -t rootbeer-node-linux .
docker run --rm --platform linux/amd64 \
  -v "$PWD":/src:ro -v rootbeer-bazel-cache:/cache rootbeer-node-linux \
  bazel --output_user_root=/cache build --symlink_prefix=/ --jobs=1 \
  //node:rootbeer_22 //node:dist_22 --output_groups=+dist
```

On Apple Silicon, Docker emulates x86_64. It is slow.

## Test

```sh
bazel test //tests:source_22_test //tests:hermetic_22_test //tests:network_22_test
```

- `source`: checks the patched source.
- `hermetic`: runs the binary against a local TLS server.
- `network`: connects to public hosts and the eMudhra hosts. It needs the network.

A network error is a test error. It is never a pass.

## Artifacts

`bazel run //:dist_22` copies one line to `./dist/`.
`bazel run //:dist` copies all lines.
Each archive is `node-v<version>-rootbeer-<os>-<arch>.tar.gz` with a `.sha256` file.
Reproducibility is proven for one pair only. Node 22 on macOS gave the same bytes in two builds.
Node 16 on macOS did not. [docs/HERMETICITY.md](docs/HERMETICITY.md#reproducibility) has the results.

## CI

- A push to `main` or a manual run builds Node 16, 18, 20, 22, 24, and 26 on macOS 14 and Linux.
  A pull request builds only the oldest and the newest line.
  Each build job runs the three tests, then uploads the archive.
- CI reads the build matrix from `runtimes/*.json`. A new manifest adds its runtime to CI.
  `tests/runtimes_test.py` checks the manifests.
- A pull request waits for the owner to approve it in the `pr-approval` environment.
- A pull request never uses a self-hosted runner. `tests/ci_test.py` checks this.
- A push to `main` uses the runner in the `CI_RUNS_ON` variable. Without it, GitHub hosts the job.
- Bazel is pinned and checked by sha256. Each action has a commit SHA.

## Known gaps

- Not fully hermetic. On macOS, the SDK and POSIX tools come from the host.
- A host store with emSign roots makes the binary trust emSign hosts.

[docs/HERMETICITY.md](docs/HERMETICITY.md) lists what is pinned and what is not.
[docs/EMUDHRA.md](docs/EMUDHRA.md) describes the eMudhra test hosts.

## Names

The project is `rootbeer-node`. Identifiers already use `rootbeer`:
Bazel targets, `ROOTBEER_*` variables, and archive names.
The repository was `systemca-nodejs` for a short time. GitHub redirects the old address.

## License

MIT. See [LICENSE](LICENSE).
