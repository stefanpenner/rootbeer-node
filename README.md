# systemca-nodejs

Node.js 16, 18, 20, and 22 with no bundled root certificates.
Each binary uses only the local (system) trust store.

## What it does

1. It builds Node from pinned source with Bazel and a pinned toolchain.
2. It removes the bundled root certificates.
3. It forces the local trust store.
4. It tests that the binary starts and connects to valid hosts.
   It also tests that the binary fails against the eMudhra test hosts when the local store has no emSign roots.

`MODULE.bazel` holds the source pins. Each checksum comes from the release `SHASUMS256.txt`.

| Line | Version | Source sha256 | macOS arm64 | Linux x86_64 |
|---|---|---|---|---|
| 22 | 22.23.4 | `4dd79de8cdc85d65cb32f48a75aee1067bf00bf94b96ecc8e4c2f82f6f0272c2` | pass | pass |
| 20 | 20.20.2 | `8cb85a81f75169eb811f7b2512cf17a646826430debbe016a7461f31e286fdef` | pass | pass |
| 18 | 18.20.8 | `ec60a6d2344ef9e1f093991ca1bb6bbe92c61c29d1762c4b99e08f87dbb91e2f` | pass | pass |
| 16 | 16.20.2 | `33188eb11b977113adb65b2e09d71bddd63f12168ba73ceadae6c27938dc9e93` | pass | pass |

"Pass" means that the source, hermetic, and network tests passed.
[STATUS.md](STATUS.md) gives the evidence for each result.

Node 16 and 18 are past end of life. They get no upstream security fixes.

## Threat model

The binary holds no root certificates. All trust comes from the host.

- A root that you remove from the host store stops working for each new process. You do not need a new Node release.
- A root that stays in the host store stays trusted.
  This project does not remove a bad root from your host.
- `tls.rootCertificates` is empty.
- `--use-bundled-ca` has no effect.
- `NODE_EXTRA_CA_CERTS` still adds a root.
- OpenSSL reads the store from `SSL_CERT_FILE`, `SSL_CERT_DIR`, or `/etc/ssl`.
  A person who can set these variables or write to these paths controls the trust of the process.
- A host with no store gets no trust. Each TLS connection then fails.

## Platforms

- **macOS arm64 (macOS 14 or later):** All four lines build and pass the tests.
- **Linux x86_64:** All four lines build and pass the tests. The binary needs glibc 2.25 or later, and a test fails if that rises above 2.31.

## Layout

| Path | Content |
|---|---|
| `MODULE.bazel` | Pins for the Node source, the stock Node controls, and the toolchain |
| `versions.bzl` | The Node lines |
| `patches/<line>/` | The patches for each Node line |
| `bazel/` | The `node_build` rule, the build driver, and the toolchain repositories |
| `node/` | The build and archive targets |
| `tests/` | The source, hermetic, network, image, and CI tests |
| `trust/` | The pinned test CA bundle |
| `docker/` | The Linux build image |
| `tools/` | The scripts that make patches, bundles, and `.deb` pins, and that collect archives |

## Patches

`tools/make_patches.py` makes the patches from the pristine source.

| Patch | Lines | What it does |
|---|---|---|
| `0001-empty-root-certs` | All | Empties `src/node_root_certs.h` |
| `0002-force-local-store` | All | Makes Node read only the local store |
| `0003-libcxx-19-char-traits` | 16, 18 | Lets the source compile with libc++ 19 |
| `0004-zlib-macos-test` | 16, 18 | Fixes a macOS check in `zutil.h` |

Patch `0002` differs between lines:

- **16, 18, 20:** The patch changes the older root store code in `src/crypto/crypto_context.cc`.
- **22:** The patch changes the newer root store code in the same file. `GetBundledRootCertificates` returns an empty list. `--use-system-ca` still works.

The patch also changes `src/node_options.cc` and the OpenSSL `.gypi` files.

## Build

Install Bazel. Then do this:

```sh
bazel build //node:rootbeer_22 //node:dist_22 --output_groups=+dist
```

Change `22` to build a different line.

On Linux or in a container, use the Docker image.
The image holds only pinned files. Build it from the repository root:

```sh
docker build --platform linux/amd64 -f docker/Dockerfile -t systemca-nodejs-linux .
docker run --rm --platform linux/amd64 \
  -v "$PWD":/src:ro -v systemca-bazel-cache:/cache systemca-nodejs-linux \
  bazel --output_user_root=/cache build --lockfile_mode=off --symlink_prefix=/ --jobs=1 \
  //node:rootbeer_22 //node:dist_22 --output_groups=+dist
```

On Apple Silicon, Docker emulates x86_64. The build is slow.

## Test

```sh
bazel test //tests:source_22_test //tests:hermetic_22_test //tests:network_22_test
```

- `source_N_test` checks the patched source.
- `hermetic_N_test` runs the binary against a local TLS server.
- `network_N_test` connects to public hosts and to the eMudhra hosts. It needs the network.

A network error gives a test error. It never gives a pass.

## Artifacts

Run `bazel run //:dist_22` to copy one line to `./dist/`.
Run `bazel run //:dist` to copy all lines.

Each line gives two files:

- `node-v<version>-rootbeer-<os>-<arch>.tar.gz`
- `node-v<version>-rootbeer-<os>-<arch>.tar.gz.sha256`

The archives from the status run have these checksums.
No test proves that a new build gives the same bytes.

| File | sha256 |
|---|---|
| `node-v22.23.4-rootbeer-darwin-arm64.tar.gz` | `d1d1065deeebee799e0b964e4df38ea3325ded9ed0598eb9b0cdbe645037ac00` |
| `node-v20.20.2-rootbeer-darwin-arm64.tar.gz` | `4d460020a487d033721fc6bdb5b82e67f8bf7eff8fb01950271f0fa34e98bbed` |
| `node-v18.20.8-rootbeer-darwin-arm64.tar.gz` | `41c0f99b142fe6539f0c103bdce1f9b428a6f66dde7346521042b328a0511e85` |
| `node-v16.20.2-rootbeer-darwin-arm64.tar.gz` | `b19d2acb290dabd2919ad49d5fa78a4824f8329cb45e4ef455b705034995fc49` |
| `node-v22.23.4-rootbeer-linux-x64.tar.gz` | `9aa2f1301faa321423612eb3de7e7ba286f41de4dd89bd6b7a92be442a540d09` |
| `node-v20.20.2-rootbeer-linux-x64.tar.gz` | `aeee2abed4f0aa36f0934d26b649edfb5ddab966393d3e4a748e28d1d9a0f62e` |
| `node-v18.20.8-rootbeer-linux-x64.tar.gz` | `a755d921d4712b2f8037a5e7c0a933f8be1545a179c13ca6536e9f996054a127` |
| `node-v16.20.2-rootbeer-linux-x64.tar.gz` | `3265d9334a8d1f4acc79e3dfdc883e7023efc20f4b0e9601dc7b7a46d699c4de` |

## Known gaps

- The build is not fully hermetic. On macOS, the SDK and the POSIX tools come from the host.
- OpenSSL does not check revocation. A revoked certificate does not fail for this reason.
- The host store can contain emSign roots. The binary then trusts the emSign hosts.
- Only Node 16 and 22 have a Linux build in a container. The other Linux results come from a hosted CI runner.

[STATUS.md](STATUS.md) and [docs/HERMETICITY.md](docs/HERMETICITY.md) give the full list.

## Names

The project was called `rootbeer`. Some names keep the old prefix:

- Bazel targets, for example `//node:rootbeer_22`
- `ROOTBEER_*` environment variables
- The artifact file names

## More information

- [docs/HERMETICITY.md](docs/HERMETICITY.md): what is pinned and what is not
- [docs/EMUDHRA.md](docs/EMUDHRA.md): the eMudhra test hosts

## CI

- A push to `main` and a manual run use the runner in the repository variable `CI_RUNS_ON`.
  Without the variable, GitHub hosts the job.
- A pull request always uses a GitHub-hosted runner.
  It waits until the owner approves the run in the `pr-approval` environment.
- Runs from outside contributors always need approval.
- A pull request never uses a self-hosted runner. `tests/ci_test.py` checks this rule.
- Each run builds Node 16, 18, 20, and 22 on macOS 14 and on Linux.
  Each build runs the source, hermetic, and network tests, then uploads the archive as an artifact.
- Bazel comes from a pinned release. The job checks the sha256 before it runs the binary.
  Each action in a workflow has a commit SHA.

## License

MIT. See [LICENSE](LICENSE).
