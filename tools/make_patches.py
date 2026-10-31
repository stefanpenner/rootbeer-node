#!/usr/bin/env python3
"""Regenerates patches/ from verified Node source trees.

Usage: make_patches.py <directory that holds node-vX.Y.Z trees> <patches directory>

Every replacement must match exactly once. A new Node release that moves the
trust code stops this tool instead of producing a partial patch.
"""

import difflib
import os
import re
import sys

VERSIONS = {"22": "22.23.4", "20": "20.20.2", "18": "18.20.8", "16": "16.20.2"}

EMPTY_HEADER = """\
// rootbeer: This file holds no certificates. Trust comes from the local store.
"""

STORE_COMMENT = """\
  // rootbeer: The binary holds no roots. The OpenSSL default paths are the only
  // default trust source. They honor SSL_CERT_FILE and SSL_CERT_DIR. No flag
  // changes this choice.
"""


def substitute(pattern, replacement, text, name):
    result, count = re.subn(pattern, lambda _: replacement, text, flags=re.S)
    if count != 1:
        raise SystemExit(f"{name}: expected one match, found {count}: {pattern}")
    return result


def remove_literal(literal, text, name):
    return substitute(re.escape(literal), "", text, name)


def legacy_context(text, name):
    """Node 16, 18, and 20 share one shape of the trust code."""
    text = substitute(
        r"static const char\* const root_certs\[\] = \{\n"
        r'#include "node_root_certs.h"  // NOLINT\(build/include_order\)\n'
        r"\};\n\n",
        "", text, name)
    text = substitute(
        r"  static std::vector<X509\*> root_certs_vector;.*?"
        r"(  X509_STORE\* store = X509_STORE_new\(\);)",
        "  X509_STORE* store = X509_STORE_new();", text, name)
    text = substitute(
        r"  if \(per_process::cli_options->ssl_openssl_cert_store\) \{\n"
        r"    X509_STORE_set_default_paths\(store\);\n"
        r"  \} else \{.*?\n  \}\n\n  return store;",
        STORE_COMMENT + "  X509_STORE_set_default_paths(store);\n\n  return store;",
        text, name)
    text = substitute(
        r"  Local<Value> result\[arraysize\(root_certs\)\];.*?"
        r"Array::New\(env->isolate\(\), result, arraysize\(root_certs\)\)\);",
        "  args.GetReturnValue().Set(Array::New(env->isolate()));", text, name)
    return text


def modern_context(text, name):
    """Node 22 loads bundled roots through a cached vector."""
    text = substitute(
        r"static const char\* const root_certs\[\] = \{\n"
        r'#include "node_root_certs.h"  // NOLINT\(build/include_order\)\n'
        r"\};\n\n",
        "", text, name)
    text = substitute(
        r"  // Read the bundled certificates in node_root_certs.h into\n.*?"
        r"  return bundled_root_certs;\n\}\n\n// TODO\(joyeecheung\)",
        "  // rootbeer: The binary holds no roots.\n  return {};\n}\n\n// TODO(joyeecheung)",
        text, name)
    text = substitute(
        r"  if \(per_process::cli_options->ssl_openssl_cert_store\) \{\n"
        r"    CHECK_EQ\(1, X509_STORE_set_default_paths\(store\)\);\n"
        r"  \} else \{\n"
        r"    for \(X509\* cert : GetBundledRootCertificates\(\)\) \{\n"
        r"      CHECK_EQ\(1, X509_STORE_add_cert\(store, cert\)\);\n"
        r"    \}\n"
        r"    if \(per_process::cli_options->use_system_ca\) \{\n"
        r"      for \(X509\* cert : GetSystemStoreCACertificates\(\)\) \{\n"
        r"        CHECK_EQ\(1, X509_STORE_add_cert\(store, cert\)\);\n"
        r"      \}\n"
        r"    \}\n"
        r"  \}\n",
        STORE_COMMENT
        + "  CHECK_EQ(1, X509_STORE_set_default_paths(store));\n"
        + "  if (per_process::cli_options->use_system_ca) {\n"
        + "    for (X509* cert : GetSystemStoreCACertificates()) {\n"
        + "      CHECK_EQ(1, X509_STORE_add_cert(store, cert));\n"
        + "    }\n"
        + "  }\n",
        text, name)
    text = substitute(
        r"  Local<Value> result\[arraysize\(root_certs\)\];.*?"
        r"Array::New\(env->isolate\(\), result, arraysize\(root_certs\)\)\);",
        "  args.GetReturnValue().Set(Array::New(env->isolate()));", text, name)
    return text


def options(text, name):
    text = substitute(
        r'  if \(use_openssl_ca && use_bundled_ca\) \{\n'
        r'    errors->push_back\("either --use-openssl-ca or --use-bundled-ca can be "\n'
        r'                      "used, not both"\);\n'
        r"  \}\n\n",
        "", text, name)
    return remove_literal(
        '  ImpliesNot("--use-bundled-ca", "[ssl_openssl_cert_store]");\n', text, name)


def openssl_dir(text, name):
    return substitute(
        r'OPENSSLDIR="/System/Library/OpenSSL/"', 'OPENSSLDIR="/etc/ssl"', text, name)


def edits_for(major):
    context = modern_context if major == "22" else legacy_context
    edits = {
        "src/crypto/crypto_context.cc": context,
        "src/node_options.cc": options,
        "deps/openssl/openssl_common.gypi": openssl_dir,
    }
    if major == "16":
        edits["deps/openssl/openssl.gypi"] = openssl_dir
    return edits


def unified(path, before, after):
    # The Bazel patch reader needs the git header to split a multi-file patch.
    return f"diff --git a/{path} b/{path}\n" + "".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), f"a/{path}", f"b/{path}"))


def read(root, path):
    with open(os.path.join(root, path), encoding="utf-8", newline="") as stream:
        return stream.read()


def write(patches, major, name, text):
    directory = os.path.join(patches, major)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name), "w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def main():
    sources, patches = sys.argv[1:]
    for major, version in VERSIONS.items():
        root = os.path.join(sources, f"node-v{version}")
        header = "src/node_root_certs.h"
        write(patches, major, "0001-empty-root-certs.patch",
              unified(header, read(root, header), EMPTY_HEADER))
        forced = ""
        for path, edit in edits_for(major).items():
            before = read(root, path)
            forced += unified(path, before, edit(before, f"{major}:{path}"))
        write(patches, major, "0002-force-local-store.patch", forced)


if __name__ == "__main__":
    main()
