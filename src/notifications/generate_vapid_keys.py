#!/usr/bin/env python3
"""
CLI Utility to generate standards-compliant VAPID keys for AI Dincharya Web Push.

Usage:
    .venv/bin/python -m src.notifications.generate_vapid_keys
"""

import sys
from pathlib import Path

# Add project root to path
repo_root = str(Path(__file__).resolve().parent.parent.parent)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.notifications.push_service import generate_vapid_key_pair

def main():
    keys = generate_vapid_key_pair()
    print("=" * 60)
    print("AI DINCHARYA: Standards-Compliant VAPID Keypair Generated")
    print("=" * 60)
    print(f"VAPID_PUBLIC_KEY={keys['public_key']}")
    print(f"VAPID_PRIVATE_KEY={keys['private_key']}")
    print("VAPID_CLAIMS_EMAIL=mailto:admin@aidincharya.internal")
    print("=" * 60)
    print("Add the above keys to your .env file to enable Web Push notifications.")

if __name__ == "__main__":
    main()
