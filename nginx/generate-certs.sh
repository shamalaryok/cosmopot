#!/bin/bash

# Generate self-signed certificate for development (TLS 1.3)
# This script creates a certificate valid for 365 days

set -e

CERT_DIR="$(dirname "$0")"
mkdir -p "$CERT_DIR/certs"

# Check if certificates already exist
if [ -f "$CERT_DIR/certs/server.crt" ] && [ -f "$CERT_DIR/certs/server.key" ]; then
    echo "Certificates already exist at $CERT_DIR/certs/"
    exit 0
fi

echo "Generating self-signed certificate for development..."

# Generate private key (4096-bit RSA)
openssl genrsa -out "$CERT_DIR/certs/server.key" 4096

# Generate certificate signing request
openssl req -new \
    -key "$CERT_DIR/certs/server.key" \
    -out "$CERT_DIR/certs/server.csr" \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# Self-sign the certificate (365 days validity)
openssl x509 -req \
    -in "$CERT_DIR/certs/server.csr" \
    -signkey "$CERT_DIR/certs/server.key" \
    -out "$CERT_DIR/certs/server.crt" \
    -days 365 \
    -extensions v3_alt \
    -extfile <(printf "subjectAltName=DNS:localhost,DNS:*.local,IP:127.0.0.1")

# Remove CSR
rm "$CERT_DIR/certs/server.csr"

# Set appropriate permissions
chmod 600 "$CERT_DIR/certs/server.key"
chmod 644 "$CERT_DIR/certs/server.crt"

echo "Self-signed certificate generated successfully!"
echo "Certificate location: $CERT_DIR/certs/"
echo ""
echo "Note: This certificate is for development only."
echo "For production, use certificates from a trusted CA."
