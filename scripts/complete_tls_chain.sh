#!/usr/bin/env bash
# Complete a meeting site's TLS chain when the server forgets to send its
# intermediate certificate(s).
#
# Browsers fetch a missing intermediate from the leaf's "CA Issuers" (AIA)
# URL, so such a site looks fine to people, while curl, Python and Node
# (Claude Code's WebFetch) refuse it with "unable to get local issuer
# certificate". This script does what browsers do, and nothing more:
#
#   * it fetches at most 3 intermediates, each named by the AIA URL of the
#     certificate below it, and keeps them only if each is a CA certificate
#     and the whole chain then verifies, by OpenSSL, against the system root
#     store, for purpose sslserver and for HOST's name;
#   * expired, self-signed, wrong-host or otherwise invalid certificates
#     still fail, because none of that is fixed by adding an intermediate.
#
# Usage: complete_tls_chain.sh HOST OUTDIR
#
# When HOST needed (and got) a completed chain, the intermediates are appended
# to OUTDIR/extra-ca.pem and OUTDIR/ca-bundle.pem is rewritten as the system
# bundle plus all of them. Point NODE_EXTRA_CA_CERTS at extra-ca.pem and
# CURL_CA_BUNDLE / SSL_CERT_FILE at ca-bundle.pem. Nothing is written when the
# chain is already complete or cannot be completed. The script prints one
# status line and exits 0 in all three cases (callers then fetch as usual and
# fail closed); it exits 2 only on a bad invocation.

set -uo pipefail

host="${1:-}"
outdir="${2:-}"
sys_bundle="${SYSTEM_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"

if [[ -z "$host" || -z "$outdir" || $# -ne 2 ]]; then
  echo "usage: $0 HOST OUTDIR" >&2
  exit 2
fi
host="${host,,}"
host="${host%.}"
if [[ ! "$host" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ \
      || "${host##*.}" =~ ^[0-9]+$ ]]; then
  echo "complete_tls_chain: '$1' is not a plain DNS host name" >&2
  exit 2
fi
if [[ ! -s "$sys_bundle" ]]; then
  echo "complete_tls_chain: system CA bundle $sys_bundle not found" >&2
  exit 2
fi

work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT

say() { echo "complete_tls_chain: $host: $*"; }

if ! timeout 20 openssl s_client -connect "$host:443" -servername "$host" -showcerts \
      </dev/null >"$work/sclient.txt" 2>/dev/null; then
  if ! grep -q 'BEGIN CERTIFICATE' "$work/sclient.txt"; then
    say "no TLS certificate received; left as is"
    exit 0
  fi
fi

# Split the served chain: leaf.pem, and every other served cert in served.pem.
awk -v dir="$work" '
  /-----BEGIN CERTIFICATE-----/ { n++; inside = 1 }
  inside { print > (dir "/cert" n ".pem") }
  /-----END CERTIFICATE-----/ { inside = 0 }
' "$work/sclient.txt"
if [[ ! -s "$work/cert1.pem" ]]; then
  say "no TLS certificate received; left as is"
  exit 0
fi
mv "$work/cert1.pem" "$work/leaf.pem"
cat "$work"/cert[0-9]*.pem > "$work/served.pem" 2>/dev/null || : > "$work/served.pem"

verifies() {  # $1 = file of untrusted intermediates
  openssl verify -CAfile "$sys_bundle" -untrusted "$1" -purpose sslserver \
    -verify_hostname "$host" "$work/leaf.pem" >/dev/null 2>&1
}

# An empty -untrusted file is an error for openssl, so always include the leaf.
cat "$work/served.pem" "$work/leaf.pem" > "$work/untrusted.pem"
if verifies "$work/untrusted.pem"; then
  say "chain already complete"
  exit 0
fi

: > "$work/fetched.pem"
cur="$work/leaf.pem"
for i in 1 2 3; do
  url="$(openssl x509 -in "$cur" -noout -ext authorityInfoAccess 2>/dev/null \
         | sed -n 's/.*CA Issuers - URI:\(https\{0,1\}:\/\/[^[:space:],]*\).*/\1/p' | head -n 1)"
  if [[ -z "$url" ]]; then
    say "chain invalid and no CA Issuers URL to complete it; left as is"
    exit 0
  fi
  if ! curl -q -sS --fail --max-time 15 --max-filesize 65536 --proto '=http,https' \
        -o "$work/aia$i" "$url" 2>/dev/null; then
    say "could not download intermediate from $url; left as is"
    exit 0
  fi
  if ! openssl x509 -inform DER -in "$work/aia$i" -out "$work/int$i.pem" 2>/dev/null \
      && ! openssl x509 -inform PEM -in "$work/aia$i" -out "$work/int$i.pem" 2>/dev/null; then
    say "file at $url is not a single certificate; left as is"
    exit 0
  fi
  if ! openssl x509 -in "$work/int$i.pem" -noout -ext basicConstraints 2>/dev/null | grep -q 'CA:TRUE'; then
    say "certificate at $url is not a CA certificate; left as is"
    exit 0
  fi
  cat "$work/int$i.pem" >> "$work/fetched.pem"
  cat "$work/served.pem" "$work/leaf.pem" "$work/fetched.pem" > "$work/untrusted.pem"
  if verifies "$work/untrusted.pem"; then
    mkdir -p "$outdir"
    cat "$work/fetched.pem" >> "$outdir/extra-ca.pem"
    cat "$sys_bundle" "$outdir/extra-ca.pem" > "$outdir/ca-bundle.pem"
    say "completed the chain with $i intermediate(s) from its CA Issuers URL"
    exit 0
  fi
  cur="$work/int$i.pem"
done

say "chain still does not verify after fetching intermediates; left as is"
exit 0
