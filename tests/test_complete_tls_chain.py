"""Offline checks of scripts/complete_tls_chain.sh's input validation.

The chain-completion path itself needs live TLS servers, so it is not run
here; the script refuses anything but a plain DNS name before any network
access, which is what these tests pin down.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "complete_tls_chain.sh"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=30)


class CompleteTlsChainArgs(unittest.TestCase):
    def test_rejects_non_dns_hosts_without_writing(self):
        bad = ["1.2.3.4", "localhost", "-servername", "a b.org", "x.org:8443", "x.org/evil",
               "https://x.org", "-x.org", "x-.org", "x..org", ""]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "tls"
            for host in bad:
                with self.subTest(host=host):
                    self.assertEqual(run(host, str(out)).returncode, 2)
            self.assertFalse(out.exists())

    def test_requires_exactly_two_arguments(self):
        self.assertEqual(run().returncode, 2)
        self.assertEqual(run("example.org").returncode, 2)
        self.assertEqual(run("example.org", "a", "b").returncode, 2)


if __name__ == "__main__":
    unittest.main()
