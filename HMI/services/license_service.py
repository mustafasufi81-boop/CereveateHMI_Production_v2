"""
License Service — ECDSA-Signed Activation Key Validation
Design reference: PLANT_AREA_ACCESS_CONTROL_DESIGN.md §16, §27.1

SECURITY ARCHITECTURE:
  - Vendor holds Ed25519 private key (never on server)
  - Public key loaded from config['license']['public_key_hex'] (hex string, 64 chars)
  - Activation key format: base64url(payload_json) + '.' + base64url(ed25519_signature)
  - max_users DB column is CACHED DISPLAY ONLY — runtime checks always verify signature
  - A DB admin cannot bypass limits by editing max_users column
  - There is NO bypass mode — license enforcement is database-driven and cannot be
    disabled via config file, environment variable, or code flag

Payload format (signed by vendor):
  { "customer": "ABC Steel", "max_users": 50, "max_areas": null, "expiry": "2027-01-01" }

EXPIRY POLICY (enforced at activation and at every runtime check):
  - 'expiry' field is MANDATORY in every signed payload — keys without it are rejected
  - Maximum allowed term is 366 days from today (no multi-year or perpetual keys)
  - Keys are automatically deactivated at runtime when valid_until < NOW() (DB-level)
  - Signature is re-verified against expiry on every cache miss (max every 60 s)
"""

import base64
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# ── Cache constants ─────────────────────────────────────────────────────────
_VERIFIED_CACHE_TTL_SECONDS = 60   # re-verify signature at most once per minute
_MAX_KEY_TERM_DAYS = 366            # no key may be valid for more than 366 days from today


class LicenseService:
    """
    Manages license key activation, verification, and seat-count enforcement.

    Thread-safe in-memory cache for verified max_users (60s TTL).
    Cache stores the result of _get_verified_max_users() so we don't verify
    the Ed25519 signature on every user-creation request.
    """

    def __init__(self, db_config: dict, public_key_hex: str | None = None):
        """
        Args:
            db_config:       psycopg2 connect dict (from config.json 'database' key)
            public_key_hex:  Hex-encoded Ed25519 public key (32 bytes = 64 hex chars).
                             Load from config; NEVER from DB. If None, all seat checks
                             return 0 (no valid license) until a key is configured.
        """
        self.db_config = db_config
        self._public_key_hex = public_key_hex

        # Cache: (timestamp, max_users_int)
        self._cache_lock = threading.Lock()
        self._cached_at: float = 0.0
        self._cached_max_users: int = 0

        if not public_key_hex:
            logger.warning("[License] No public key configured — license checks will return 0 seats until activated.")

    # ─────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────

    def _get_conn(self):
        return db_pool.get_conn()

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """SHA-256 hash of the raw activation key (stored in DB as key_hash)."""
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    def _verify_payload(self, signed_payload: str) -> dict | None:
        """
        Verifies the Ed25519 signature and returns the decoded JSON payload dict.
        Returns None if signature is invalid, malformed, or public key is missing.

        Signed payload format:
            base64url(payload_json_bytes) + '.' + base64url(ed25519_signature_bytes)
        """
        if not self._public_key_hex:
            logger.error("[License] Cannot verify — public key not configured.")
            return None

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.exceptions import InvalidSignature

            parts = signed_payload.strip().split('.')
            if len(parts) != 2:
                logger.error("[License] Malformed signed_payload — expected exactly one '.' separator.")
                return None

            # Decode: add padding back (base64url strips '=')
            payload_bytes = base64.urlsafe_b64decode(parts[0] + '==')
            signature     = base64.urlsafe_b64decode(parts[1] + '==')

            public_key_bytes = bytes.fromhex(self._public_key_hex)
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

            public_key.verify(signature, payload_bytes)   # raises InvalidSignature if tampered
            return json.loads(payload_bytes.decode('utf-8'))

        except Exception as exc:
            # InvalidSignature, json decode error, hex decode error — all treated as invalid
            logger.error(f"[License] Payload verification failed: {exc}")
            return None

    def _get_verified_max_users(self) -> int:
        """
        AUTHORITATIVE seat limit.
        Reads signed_payload from DB, verifies Ed25519 signature, extracts max_users.
        Result is cached for _VERIFIED_CACHE_TTL_SECONDS.

        SECURITY: Never reads max_users column directly — only from verified payload.
        Returns 0 on any error (tampered, missing key, no active license).
        """
        now = time.monotonic()
        with self._cache_lock:
            if now - self._cached_at < _VERIFIED_CACHE_TTL_SECONDS:
                return self._cached_max_users

        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT signed_payload
                        FROM historian_meta.license_keys
                        WHERE is_active = true
                          AND valid_until IS NOT NULL
                          AND valid_until > NOW()
                        LIMIT 1
                    """)
                    row = cur.fetchone()

            if not row:
                logger.warning("[License] No active, non-expired license key found.")
                with self._cache_lock:
                    self._cached_at = now
                    self._cached_max_users = 0
                return 0

            payload = self._verify_payload(row['signed_payload'])
            if payload is None:
                # Tampered or invalid — treat as no license
                with self._cache_lock:
                    self._cached_at = now
                    self._cached_max_users = 0
                return 0

            # Check payload expiry — MANDATORY field, no perpetual keys allowed
            expiry_str = payload.get('expiry')
            if not expiry_str:
                logger.error("[License] Payload missing mandatory 'expiry' field — key rejected.")
                with self._cache_lock:
                    self._cached_at = now
                    self._cached_max_users = 0
                return 0
            try:
                expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expiry:
                    logger.warning("[License] License payload has expired (payload.expiry=%s).", expiry_str)
                    with self._cache_lock:
                        self._cached_at = now
                        self._cached_max_users = 0
                    return 0
            except ValueError:
                logger.error("[License] Payload 'expiry' is malformed ('%s') — key rejected.", expiry_str)
                with self._cache_lock:
                    self._cached_at = now
                    self._cached_max_users = 0
                return 0

            max_users = int(payload.get('max_users', 0))
            with self._cache_lock:
                self._cached_at = now
                self._cached_max_users = max_users
            logger.debug("[License] Verified max_users=%d from signed payload.", max_users)
            return max_users

        except Exception as exc:
            logger.error(f"[License] _get_verified_max_users error: {exc}")
            return 0

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def check_user_creation_allowed(self) -> tuple[bool, int, int]:
        """
        Returns (allowed: bool, current_count: int, max_users: int).

        Rules:
          - Admin role users (is_admin=true) are EXCLUDED from seat count
          - Users with status='deactivated' or 'rejected' are NOT counted
          - Users with status='pending' ARE counted (reservation hold)
          - max_users is from ECDSA-verified signed_payload only
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT COUNT(*) AS current_count
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON r.id = u.role_id
                        WHERE u.status IN ('approved', 'pending')
                          AND r.is_admin = false
                    """)
                    current_count = cur.fetchone()['current_count']

            max_users = self._get_verified_max_users()
            allowed = (current_count < max_users)
            return allowed, int(current_count), max_users

        except Exception as exc:
            logger.error(f"[License] check_user_creation_allowed error: {exc}")
            # On DB error: fail-safe — deny creation, don't bypass limit
            return False, 0, 0

    def get_status(self) -> dict:
        """
        Returns display information for the Admin Console license banner.
        Never exposes the raw signed_payload to the frontend.
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, key_label, max_users, issued_to, issued_at,
                               valid_until, is_active, activated_at, signed_payload
                        FROM historian_meta.license_keys
                        WHERE is_active = true
                        LIMIT 1
                    """)
                    row = cur.fetchone()

                    cur.execute("""
                        SELECT COUNT(*) AS cnt
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON r.id = u.role_id
                        WHERE u.status IN ('approved', 'pending')
                          AND r.is_admin = false
                    """)
                    current_count = cur.fetchone()['cnt']

            if not row:
                return {'is_valid': False, 'key_label': None, 'max_users': 0,
                        'current_users': current_count, 'valid_until': None, 'issued_to': None}

            # Verify signature to get authoritative max_users
            payload = self._verify_payload(row['signed_payload'])
            is_valid = payload is not None
            verified_max = int(payload.get('max_users', 0)) if payload else 0

            # Check expiry
            if row['valid_until'] and datetime.now(timezone.utc) > row['valid_until']:
                is_valid = False

            return {
                'is_valid': is_valid,
                'key_label':    row['key_label'],
                'max_users':    verified_max,
                'current_users': int(current_count),
                'valid_until':  row['valid_until'].isoformat() if row['valid_until'] else None,
                'issued_to':    row['issued_to'],
                'activated_at': row['activated_at'].isoformat() if row['activated_at'] else None,
            }

        except Exception as exc:
            logger.error(f"[License] get_status error: {exc}")
            return {'is_valid': False, 'error': str(exc)}

    def activate_key(self, raw_key: str, admin_user_id: int) -> dict:
        """
        Activates a new license key.
        1. Verifies the Ed25519 signature in the key.
        2. Deactivates any existing active key.
        3. Inserts the new key.
        4. Invalidates the cached max_users.

        Returns {'success': True, 'max_users': N, 'issued_to': '...'}
        Raises ValueError with user-friendly message on any failure.
        """
        if not raw_key or not raw_key.strip():
            raise ValueError("Activation key cannot be empty.")

        raw_key = raw_key.strip()
        payload = self._verify_payload(raw_key)
        if payload is None:
            raise ValueError(
                "Invalid activation key — signature verification failed. "
                "The key may be tampered, expired, or not issued for this server."
            )

        max_users = int(payload.get('max_users', 0))
        issued_to = payload.get('customer', '')
        max_areas = payload.get('max_areas', None)

        # ── Expiry: mandatory, must parse, max _MAX_KEY_TERM_DAYS from today ──
        expiry_str = payload.get('expiry')
        if not expiry_str:
            raise ValueError(
                "This activation key has no expiry date. "
                "Perpetual keys are not permitted — please request a new dated key from Cereveate."
            )
        try:
            valid_until = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"Activation key contains a malformed expiry date: '{expiry_str}'.")

        now_utc = datetime.now(timezone.utc)
        if now_utc > valid_until:
            raise ValueError(f"This license key already expired on {expiry_str}.")

        max_allowed_until = now_utc + timedelta(days=_MAX_KEY_TERM_DAYS)
        if valid_until > max_allowed_until:
            raise ValueError(
                f"This activation key is valid until {expiry_str}, which exceeds the "
                f"maximum allowed term of {_MAX_KEY_TERM_DAYS} days. "
                "Please request a key with a shorter validity period."
            )

        key_hash = self._hash_key(raw_key)
        key_label = f"{issued_to} — {max_users} seats"

        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # Deactivate existing active key
                    cur.execute("""
                        UPDATE historian_meta.license_keys
                        SET is_active = false
                        WHERE is_active = true
                    """)

                    # Insert new key
                    cur.execute("""
                        INSERT INTO historian_meta.license_keys
                            (key_hash, key_label, signed_payload, max_users, max_areas,
                             issued_to, valid_until, is_active, activated_by, activated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s, NOW())
                        ON CONFLICT (key_hash) DO UPDATE
                            SET is_active    = true,
                                activated_by = EXCLUDED.activated_by,
                                activated_at = NOW()
                    """, (key_hash, key_label, raw_key, max_users, max_areas,
                          issued_to, valid_until, admin_user_id))
                    conn.commit()

            # Invalidate cache
            with self._cache_lock:
                self._cached_at = 0.0
                self._cached_max_users = 0

            logger.info(f"[License] Key activated by user {admin_user_id}: {key_label}")
            return {'success': True, 'max_users': max_users, 'issued_to': issued_to,
                    'valid_until': valid_until.isoformat() if valid_until else None}

        except psycopg2.Error as exc:
            logger.error(f"[License] activate_key DB error: {exc}")
            raise ValueError(f"Database error during activation: {exc}")

    def invalidate_cache(self):
        """Force re-verification on next check (call after any manual DB change)."""
        with self._cache_lock:
            self._cached_at = 0.0
