"""
One-shot license activator for Cereveate OPC Analytics Platform.

What this does:
  1. Generates a fresh Ed25519 keypair (vendor private key + public key)
  2. Signs a 1-year license payload  {customer, max_users=50, expiry=+365d}
  3. Writes public_key_hex into config.json  (license.public_key_hex)
  4. Inserts / replaces the active license row in historian_meta.license_keys
  5. Prints the private key (keep it safe — not stored anywhere on this machine)

Run once, then restart Flask.  Safe to re-run — deactivates old rows first.
"""

import base64
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── resolve paths ──────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
CONFIG_PATH  = SCRIPT_DIR / "config.json"

# ── Load DB config from config.json ───────────────────────────────────────
with open(CONFIG_PATH, encoding="utf-8") as fh:
    config = json.load(fh)

DB_CFG = config["database"]
LIC_CFG = config.setdefault("license", {})

# ── Dependencies ──────────────────────────────────────────────────────────
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:
    sys.exit(f"Missing dependency: {e}\nRun:  pip install cryptography psycopg2-binary")

# ── 1. Generate keypair ────────────────────────────────────────────────────
print("\n[1/5] Generating Ed25519 keypair…")
private_key = Ed25519PrivateKey.generate()
public_key  = private_key.public_key()

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
pub_bytes  = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
priv_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())

pub_hex  = pub_bytes.hex()
priv_hex = priv_bytes.hex()
print(f"   Public key  : {pub_hex}")
print(f"   Private key : {priv_hex}  ← SAVE THIS SOMEWHERE SAFE (not stored on server)")

# ── 2. Build + sign payload ────────────────────────────────────────────────
print("\n[2/5] Building license payload…")
expiry_date = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d")
payload_dict = {
    "customer":  "Cereveate Industrial",
    "max_users": 50,
    "max_areas": None,
    "expiry":    expiry_date,
}
payload_json  = json.dumps(payload_dict, separators=(',', ':')).encode('utf-8')
payload_b64   = base64.urlsafe_b64encode(payload_json).rstrip(b'=').decode()

signature     = private_key.sign(payload_json)
signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

signed_payload = f"{payload_b64}.{signature_b64}"
key_hash       = hashlib.sha256(signed_payload.encode('utf-8')).hexdigest()

print(f"   Customer    : {payload_dict['customer']}")
print(f"   Max users   : {payload_dict['max_users']}")
print(f"   Expiry      : {expiry_date}")
print(f"   Key hash    : {key_hash[:16]}…")

# ── 3. Verify signature before writing anything ───────────────────────────
print("\n[3/5] Verifying signature (self-check)…")
pub_key_verify = Ed25519PublicKey.from_public_bytes(pub_bytes)
try:
    pub_key_verify.verify(signature, payload_json)
    print("   ✅ Signature valid")
except Exception as exc:
    sys.exit(f"   ❌ Self-check FAILED: {exc}")

# ── 4. Update config.json with public key ─────────────────────────────────
print("\n[4/5] Writing public key to config.json…")
LIC_CFG["public_key_hex"] = pub_hex
with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
    json.dump(config, fh, indent=2)
print(f"   config.json updated  (license.public_key_hex = {pub_hex[:16]}…)")

# ── 5. Insert license into DB ──────────────────────────────────────────────
print("\n[5/5] Inserting license into historian_meta.license_keys…")
try:
    conn = psycopg2.connect(**DB_CFG)
    conn.autocommit = False
    with conn.cursor() as cur:
        # Deactivate any previous active keys
        cur.execute("""
            UPDATE historian_meta.license_keys
            SET is_active = false
            WHERE is_active = true
        """)
        deactivated = cur.rowcount
        if deactivated:
            print(f"   Deactivated {deactivated} previous active key(s)")

        # Insert new key
        cur.execute("""
            INSERT INTO historian_meta.license_keys
                (key_label, key_hash, max_users, issued_to,
                 valid_until, is_active, activated_at, signed_payload)
            VALUES (%s, %s, %s, %s,
                    %s::timestamptz, true, NOW(), %s)
            ON CONFLICT (key_hash) DO UPDATE SET
                is_active    = true,
                activated_at = NOW(),
                valid_until  = EXCLUDED.valid_until,
                signed_payload = EXCLUDED.signed_payload
        """, (
            "CEREV-2026-INTERNAL",
            key_hash,
            payload_dict["max_users"],
            payload_dict["customer"],
            expiry_date + "T23:59:59+00:00",
            signed_payload,
        ))
    conn.commit()
    conn.close()
    print("   ✅ License inserted successfully")

except psycopg2.errors.UniqueViolation as e:
    print(f"   ℹ️  Key already exists in DB (hash collision — safe): {e}")
except Exception as e:
    sys.exit(f"   ❌ DB insert failed: {e}")

# ── Done ──────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("✅  LICENSE ACTIVATED")
print("="*60)
print(f"  Label      : CEREV-2026-INTERNAL")
print(f"  Issued to  : {payload_dict['customer']}")
print(f"  Max users  : {payload_dict['max_users']}")
print(f"  Valid until: {expiry_date}")
print(f"  Public key : {pub_hex}")
print()
print("⚠️  SAVE YOUR PRIVATE KEY (not stored on this server):")
print(f"   {priv_hex}")
print()
print("Next step: restart Flask to reload config.json")
print("="*60)
