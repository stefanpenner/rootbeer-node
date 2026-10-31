# Open review findings

Date: 2026-10-31. An adversarial review found these items. They stay open.
STATUS.md has the test results. HERMETICITY.md has the rungs.

| Rank | Finding | Effect |
|---|---|---|
| 1 | `bazel test --config=remote-exec` fails in analysis. `@bazel_tools//third_party/ijar` finds no C++ toolchain. | Remote tests do not run. Remote builds do. |
| 2 | The scheduler default stops an action at 1800 s. A rule cannot change this limit. | Node 26 fits by 180 s with 6 jobs, in one run. A busy host can pass the limit. |
| 3 | Reproducibility is measured for macOS 22 (same bytes) and macOS 16 (different). | No claim for other pairs. |
| 4 | CI has not run since #13. Hosted Actions are budget-blocked. | The Linux lockfile and later Linux changes are not checked by CI. |
| 5 | The macOS action reads the SDK at its host path. | The declared files fix the cache key only. |
| 6 | Sandboxes do not prove that the build reads only declared inputs. | Network and environment are controlled. File reads are not fully. |
| 7 | macOS POSIX tools come from the host. The Mac Bazel binary has no checksum. | Two host inputs stay unpinned. |
| 8 | All downloads have one origin. The LLVM checksums are self-computed. The build does not verify `SHASUMS256.txt.asc`. | The supply chain has one point of trust. |
| 9 | `tools = runtime.files` uploads the whole Python runtime. | Small cost after the first upload. |
| 10 | A Linux remote build writes to a path that says `darwin_arm64-fastbuild`. | Cosmetic. |
