"""
Copyright 2018 Jason Litzinger
See LICENSE for details.
"""

from OpenSSL import crypto
from twisted.internet import ssl


def load_client_cert_and_key(cert_path, key_path):
    """Load client certificate and key from disk.

    :param path: The path where the credentials are stored.

    """
    with open(cert_path, 'rb') as cert_file:
        cert = ssl.Certificate.loadPEM(cert_file.read())

    with open(key_path, 'rb') as key_file:
        key = key_file.read()

    client_certs = ssl.PrivateCertificate.fromCertificateAndKeyPair(
        cert,
        ssl.KeyPair.load(key, format=crypto.FILETYPE_PEM)
    )

    return client_certs
