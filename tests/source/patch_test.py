"""Tests the patched source. These tests prove the patch without a compile."""

import unittest

from trustlib import path_from_env


class SourceCase(unittest.TestCase):
    def assertAbsent(self, needle, text):
        # assertNotIn prints the whole file on failure.
        self.assertFalse(needle in text, f"found in source: {needle!r}")


def read(env_name):
    with open(path_from_env(env_name), encoding="utf-8") as stream:
        return stream.read()


class RootCertificateHeader(SourceCase):
    def test_header_holds_no_certificate(self):
        self.assertAbsent("-----BEGIN", read("ROOT_CERTS_H"))


class CryptoContext(SourceCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("CRYPTO_CONTEXT_CC")

    def test_header_is_not_included(self):
        self.assertAbsent('#include "node_root_certs.h"', self.text)

    def test_array_is_gone(self):
        self.assertAbsent("root_certs[", self.text)

    def test_store_load_has_no_condition(self):
        self.assertAbsent("if (per_process::cli_options->ssl_openssl_cert_store) {\n    "
                         "CHECK_EQ(1, X509_STORE_set_default_paths", self.text)
        self.assertAbsent("if (per_process::cli_options->ssl_openssl_cert_store) {\n    "
                         "X509_STORE_set_default_paths", self.text)
        self.assertIn("X509_STORE_set_default_paths(store)", self.text)


class Options(SourceCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("NODE_OPTIONS_CC")

    def test_flags_do_not_conflict(self):
        self.assertAbsent("either --use-openssl-ca or --use-bundled-ca", self.text)

    def test_bundled_flag_has_no_effect_on_the_store(self):
        self.assertAbsent('ImpliesNot("--use-bundled-ca"', self.text)


class OpenSslDirectory(SourceCase):
    def test_no_directory_uses_the_macos_path(self):
        self.assertAbsent("/System/Library/OpenSSL", read("OPENSSL_COMMON_GYPI"))


if __name__ == "__main__":
    unittest.main()
