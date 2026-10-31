# rootbeerz JDK

This file describes the JDK build and its trust model.
The build uses the OpenJDK source of the newest LTS line, with an empty `cacerts`.
The JDK has no bundled root.

## Java does not read `SSL_CERT_FILE`

This is a limit of the JDK trust model. The Node build does not have this limit.

The JVM picks one trust store in this order:

1. The system property `javax.net.ssl.trustStore`.
2. The file `lib/security/jssecacerts`.
3. The file `lib/security/cacerts`.

The rootbeerz JDK has no `jssecacerts`, and its `cacerts` holds 0 entries.
With no flag, each TLS connection fails with this message:

```
the trustAnchors parameter must be non-empty
```

The operator must give the JVM a store. The JVM has no default path to the system store.

## How the system store reaches the JVM

**Linux, or a store file on any OS.** Give the path, the type, and the password if the store has one:

```sh
java -Djavax.net.ssl.trustStore=/path/to/store.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -Djavax.net.ssl.trustStorePassword=changeit \
     App
```

A PEM file is not a keystore. Use `keytool -importcert` to make a store from each PEM certificate.

**macOS.** Give a Keychain store type, and set the store path to `NONE`:

```sh
java -Djavax.net.ssl.trustStore=NONE \
     -Djavax.net.ssl.trustStoreType=KeychainStore-ROOT \
     App
```

Use `KeychainStore-ROOT` to read the system roots.
`KeychainStore` reads the user keychain items only.
I measured this with `getAcceptedIssuers` on stock Temurin 25.0.5, on one macOS arm64 host:

| Flags | Anchors |
|---|---|
| `trustStore=NONE`, `trustStoreType=KeychainStore` | 6 |
| `trustStoreType=KeychainStore`, no `trustStore` flag | 6 |
| `trustStore=NONE`, `trustStoreType=KeychainStore-ROOT` | 157 |

The count depends on the host.
The tests require more than 50 anchors with `KeychainStore-ROOT`.

## Inputs

The driver `jdk/build_jdk.py` runs as one Bazel action with no network.
Each rung has the meaning that `docs/HERMETICITY.md` gives.

| Input | Source | Rung |
|---|---|---|
| OpenJDK source, tag `jdk-25.0.5-ga` | `runtimes/jdk.json`, sha256 computed here | 1 |
| Boot JDK and stock control, Temurin 25.0.5+8 | Adoptium, sha256 in `runtimes/jdk.json` | 0 |
| `lib/shaders.metallib` | Copied from the boot JDK. See "Metal shaders". | 0 |
| GNU make 4.4.1, m4 1.4.20, autoconf 2.72 | GNU source, sha256 in `runtimes/jdk.json`, built in the action | 1 |
| Clang, lld, LLVM tools 19.1.7 | The same pin as the Node build | 1 |
| macOS SDK | Host, declared as inputs by content | 6 |
| `perl`, for autoconf | Host `/usr/bin/perl` | 6 |
| `lipo`, `otool`, `install_name_tool`, `codesign`, `mig`, `SetFile`, `xcodebuild` | Host | 6 |
| `/bin/bash`, `/bin/sh`, and POSIX tools in `/usr/bin` and `/bin` | Host | 6 |

## Metal shaders

The JDK configure requires the Xcode Metal tools on macOS.
The Metal Toolchain is an optional Xcode component. The build must not download it.
The driver puts two shims on `PATH`. `metal` writes an empty placeholder. `metallib` copies `lib/shaders.metallib` from the pinned boot JDK.

So the JDK does not compile these shaders from source. The bytes come from Temurin 25.0.5+8, which has the same source tag.
`hermetic_25_test` checks that the two files have the same sha256.

## Autoconf shim

On Darwin 27 the `autoconf` script hung in its `exec` of `autom4te`. `kill -9` did not stop the hung `perl` process, and `ps` on that process also hung.
A direct call to `autom4te` works. The driver puts a shim named `autoconf` on `PATH`. The shim calls `autom4te` with the two options that the script adds.

## Update the JDK

`runtimes/jdk.json` holds each pin. `jdk/extension.bzl` reads that file. `MODULE.bazel` holds no JDK pin.
