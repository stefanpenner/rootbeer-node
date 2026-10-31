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

| Line | Version |
|---|---|
| 22 | 22.23.4 |
| 20 | 20.20.2 |
| 18 | 18.20.8 |
| 16 | 16.20.2 |

Node 16 and 18 are past end of life. They get no upstream security fixes.

## Platforms

- **macOS arm64 (macOS 14 or later):** All four lines build and pass the tests.
- **Linux x86_64:** Node 16 builds in the Docker image and passes the source, hermetic, and network tests. The other lines are not verified yet.

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
