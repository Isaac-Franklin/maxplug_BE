import json
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings
import base64
import hashlib


def sign_payload(data: dict) -> str:
    """
    Step 1: Sort params (non-null only) and format as key=value&key=value
    """
    filtered = {k: str(v).strip() for k, v in data.items() if v not in [None, ""]}
    sorted_items = sorted(filtered.items(), key=lambda x: x[0])  # ASCII order sorting
    return "&".join(f"{k}={v}" for k, v in sorted_items)


def md5_uppercase(input_str: str) -> str:
    """ Step 2: MD5 and uppercase """
    return hashlib.md5(input_str.encode('utf-8')).hexdigest().upper()




def load_private_key(private_key_raw: str):
    """Load RSA Private Key. Supports:
    - Full PEM (PKCS1 or PKCS8)
    - Raw Base64 key without headers"""
    
    # Make sure it's always a string, not bytes
    if isinstance(private_key_raw, bytes):
        private_key_raw = private_key_raw.decode()

    # If PEM headers already included, use as-is
    if "BEGIN" in private_key_raw:
        key_data = private_key_raw.encode()
    else:
        # Assume it's raw base64, convert to PEM PKCS1 format
        key_data = b"-----BEGIN RSA PRIVATE KEY-----\n"
        key_data += b"\n".join(private_key_raw[i:i+64].encode() for i in range(0, len(private_key_raw), 64))
        key_data += b"\n-----END RSA PRIVATE KEY-----\n"
    # key_data = private_key_raw.encode()
    return serialization.load_pem_private_key(
        key_data,
        password=None,
    )


def generate_palmpay_signature(data: dict) -> str:
    """
    Full signature process for PalmPay:
    Step 1 → Step 2 → Step 3
    """
    strA = sign_payload(data)
    md5Str = md5_uppercase(strA)
    private_key = settings.MERCHANT_PRIVATE_KEY

    private_key_obj = load_private_key(private_key)
    signature = private_key_obj.sign(
        md5Str.encode(),
        padding.PKCS1v15(),
        hashes.SHA1()
    )

    return base64.b64encode(signature).decode()
