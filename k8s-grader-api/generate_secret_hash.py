#!/usr/bin/env python3
"""
Generate a new SECRET_HASH for K8s Grader API

This key is used to encrypt/decrypt API keys that contain user emails.
Run this script to generate a new key for production deployment.
"""

from cryptography.fernet import Fernet

def generate_secret_hash():
    """Generate a new Fernet key for SECRET_HASH"""
    key = Fernet.generate_key()
    return key.decode()

if __name__ == "__main__":
    print("=" * 60)
    print("K8s Grader API - Secret Hash Generator")
    print("=" * 60)
    print()
    print("Generating new SECRET_HASH...")
    print()
    
    secret_hash = generate_secret_hash()
    
    print("Your new SECRET_HASH:")
    print("-" * 60)
    print(secret_hash)
    print("-" * 60)
    print()
    print("IMPORTANT:")
    print("1. Save this key securely (password manager, AWS Secrets Manager)")
    print("2. Use this key when deploying: sam deploy --guided")
    print("3. Use this key when generating API keys")
    print("4. Never commit this key to version control")
    print("5. If you lose this key, all existing API keys will be invalid")
    print()
    print("Usage during deployment:")
    print(f"  Parameter SecretHash: {secret_hash}")
    print()
    print("=" * 60)
