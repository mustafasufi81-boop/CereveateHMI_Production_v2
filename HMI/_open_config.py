"""
_open_config.py — Encrypted Config Loader
==========================================
Replaces open('config.json') throughout the app.
Reads config.enc (AES-256-GCM) + machine.key and returns the config dict in memory.

Files required at startup (both in the same directory as this file):
  config.enc    — encrypted config (safe to store in git, useless without key)
  machine.key   — 64-char hex master key (NEVER commit to git, keep with you)

If either file is missing or the key is wrong → hard fatal error, app refuses to start.
No fallback to plaintext. No silent failure.
"""

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_ENC_PATH   = os.path.join(_BASE_DIR, 'config.enc')
_KEY_PATH   = os.path.join(_BASE_DIR, 'machine.key')
_ITERATIONS = 600_000   # PBKDF2-HMAC-SHA256 — must match _seal_config.py

# Module-level cache — decrypted once per process, never re-read from disk
_config_cache: dict | None = None


def load_config() -> dict:
    """
    Decrypt and return the application config dict.
    Result is cached — disk is read only once per process lifetime.

    Raises SystemExit on any failure (missing files, wrong key, tampered data).
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    # ── Check files exist ─────────────────────────────────────────────────────
    if not os.path.exists(_ENC_PATH):
        _fatal(
            "config.enc not found.",
            f"Expected location: {_ENC_PATH}",
            "Seal the config first:  python _seal_config.py"
        )

    if not os.path.exists(_KEY_PATH):
        _fatal(
            "machine.key not found.",
            f"Expected location: {_KEY_PATH}",
            "Place your machine.key file in the HMI directory and restart."
        )

    # ── Load key ──────────────────────────────────────────────────────────────
    try:
        with open(_KEY_PATH, 'r', encoding='ascii') as f:
            key_hex = f.read().strip()
        if len(key_hex) != 64:
            _fatal(
                "machine.key is malformed.",
                f"Expected 64 hex characters, got {len(key_hex)}.",
                "Restore the correct machine.key file."
            )
        master_key = bytes.fromhex(key_hex)
    except ValueError:
        _fatal(
            "machine.key contains invalid characters (must be 64 hex chars).",
            "Restore the correct machine.key file."
        )

    # ── Load encrypted blob ───────────────────────────────────────────────────
    with open(_ENC_PATH, 'rb') as f:
        blob = f.read()

    if len(blob) < 16 + 12 + 16:
        _fatal(
            "config.enc is too small — file is corrupt.",
            "Restore config.enc from backup or re-seal config.json."
        )

    # ── Decrypt ───────────────────────────────────────────────────────────────
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        salt       = blob[:16]
        nonce      = blob[16:28]
        ciphertext = blob[28:]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_ITERATIONS,
        )
        aes_key   = kdf.derive(master_key)
        plaintext = AESGCM(aes_key).decrypt(nonce, ciphertext, None)

    except ImportError:
        _fatal(
            "'cryptography' package is not installed.",
            "Run:  pip install cryptography"
        )
    except Exception:
        _fatal(
            "Config decryption failed.",
            "Either machine.key is incorrect or config.enc has been tampered with.",
            "Restore the correct machine.key, or re-seal config.json with _seal_config.py"
        )

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        cfg = json.loads(plaintext.decode('utf-8'))
    except Exception:
        _fatal(
            "Decrypted data is not valid JSON — config.enc may be corrupt.",
            "Re-seal config.json with _seal_config.py"
        )

    logger.info("[CONFIG] config.enc decrypted successfully.")
    _config_cache = cfg
    return cfg


def _fatal(*lines):
    """Print a clear fatal error block and exit immediately."""
    border = "=" * 66
    print(f"\n{border}", file=sys.stderr)
    print("  FATAL — Cannot start: config decryption error", file=sys.stderr)
    print(border, file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    print(border, file=sys.stderr)
    print(file=sys.stderr)
    sys.exit(1)
