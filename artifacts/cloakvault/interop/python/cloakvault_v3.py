"""
CloakVault v3 — independent Python implementation.

Written ONLY from docs/cloakvault-protocol-v3.md and
docs/cloakvault-v3-test-vector.json. The TypeScript source (src/lib) was
NOT read, ported, or translated. Any point where the spec did not fully
determine a choice is recorded in interop/python/SPEC-GAP-REPORT.md.

AEAD: AES-256-GCM-SIV from the third-party `cryptography` library
(pyca/cryptography, validated here against RFC 8452 Appendix C.2 KATs).
Reed–Solomon and Bech32 layers are hand-built from spec §3 and §4.

TEST USE ONLY.
"""

from __future__ import annotations

import hashlib
import hmac
import unicodedata

from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV

# ─────────────────────────────────────────────────────────────────────────────
# §2 Capsule layer
# ─────────────────────────────────────────────────────────────────────────────

VERSION = 0x02
CAPSULE_LEN = 49
NONCE = bytes(12)  # fixed all-zero, not stored (spec §2.2)
HKDF_INFO = bytes.fromhex("434c4f414b5641554c542d56332d43415053554c452d4b4559")
assert HKDF_INFO == b"CLOAKVAULT-V3-CAPSULE-KEY" and len(HKDF_INFO) == 25


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 HKDF-SHA256. Empty salt = zero-length byte string (spec §2.4)."""
    if len(salt) == 0:
        salt = bytes(32)  # per RFC 5869 §2.2, HMAC pads an absent salt to HashLen zeros
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    t = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]


def derive_capsule_key(vault_key: bytes) -> bytes:
    if len(vault_key) != 32:
        raise ValueError("Vault Key must be 32 bytes")
    return hkdf_sha256(vault_key, b"", HKDF_INFO, 32)


def create_capsule(seed_entropy: bytes, vault_key: bytes) -> bytes:
    if len(seed_entropy) != 32:
        raise ValueError("seed entropy must be 32 bytes")
    key = derive_capsule_key(vault_key)
    sealed = AESGCMSIV(key).encrypt(NONCE, seed_entropy, bytes([VERSION]))
    assert len(sealed) == 48  # ct(32) || tag(16)
    return bytes([VERSION]) + sealed


class CapsuleError(Exception):
    """Single typed failure — no partial plaintext (spec §2.5)."""


def open_capsule(capsule: bytes, vault_key: bytes) -> bytes:
    if len(capsule) != CAPSULE_LEN:
        raise CapsuleError("malformed length")
    if capsule[0] != VERSION:
        raise CapsuleError("invalid version")
    key = derive_capsule_key(vault_key)
    try:
        return AESGCMSIV(key).decrypt(NONCE, capsule[1:], bytes([VERSION]))
    except Exception as exc:  # library-specific InvalidTag → single typed failure
        raise CapsuleError("authentication failed") from exc


# ─────────────────────────────────────────────────────────────────────────────
# §3 Reed–Solomon RS(83,49) over GF(2^8), hand-built from the spec
# ─────────────────────────────────────────────────────────────────────────────

PRIM_POLY = 0x11D
RS_N, RS_K, RS_PARITY = 83, 49, 34

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= PRIM_POLY
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def _generator_poly(parity: int) -> list[int]:
    """g(x) = prod_{i=0..parity-1} (x - alpha^i), MSB-first (g[0] = 1)."""
    g = [1]
    for i in range(parity):
        root = _EXP[i]
        ng = g + [0]
        for j in range(len(g)):
            ng[j + 1] ^= gf_mul(g[j], root)
        g = ng
    return g


def rs_encode(data: bytes, parity: int = RS_PARITY) -> bytes:
    """Systematic: codeword = data || parity, parity = remainder of
    data(x)·x^parity mod g(x), highest-degree coefficient first (spec §3.2)."""
    g = _generator_poly(parity)
    # Polynomial long division, MSB-first. rem stored MSB-first here.
    rem = [0] * parity
    for byte in data:
        feedback = byte ^ rem[0]
        rem = rem[1:] + [0]
        if feedback != 0:
            for j in range(parity):
                rem[j] ^= gf_mul(g[j + 1], feedback)
    return bytes(data) + bytes(rem)


class RSUncorrectable(Exception):
    pass


def rs_decode(received: bytes, parity: int = RS_PARITY, erasures: list[int] | None = None) -> bytes:
    """Errors-and-erasures decode. codeword[j] = coeff of x^(n-1-j);
    X_p = alpha^(n-1-p); S_i = sum e_p X_p^i, i = 0..parity-1 (spec §3.2).
    Budget: 2·errors + erasures ≤ parity (spec §3.3)."""
    n = len(received)
    k = n - parity
    erasures = sorted(set(erasures or []))
    if len(erasures) > parity:
        raise RSUncorrectable("too many erasures")

    # Syndromes S_i = r(alpha^i), Horner MSB-first.
    S = []
    for i in range(parity):
        acc = 0
        a = _EXP[i]
        for byte in received:
            acc = gf_mul(acc, a) ^ byte
        S.append(acc)
    if all(s == 0 for s in S):
        return bytes(received[:k])

    def poly_mul(p, q):  # LSB-first
        out = [0] * (len(p) + len(q) - 1)
        for i, pi in enumerate(p):
            if pi:
                for j, qj in enumerate(q):
                    out[i + j] ^= gf_mul(pi, qj)
        return out

    # Erasure locator Γ(x) = prod (1 - X_p x), LSB-first.
    gamma = [1]
    for p in erasures:
        gamma = poly_mul(gamma, [1, _EXP[(n - 1 - p) % 255]])

    # Berlekamp–Massey initialized with Γ (errata locator).
    e = len(erasures)
    lam = list(gamma)
    b = list(gamma)
    L = e
    m = 1
    bcoef = 1
    for i in range(e, parity):
        delta = 0
        for j in range(len(lam)):
            if j <= i:
                delta ^= gf_mul(lam[j], S[i - j])
        if delta == 0:
            m += 1
        elif 2 * L <= i + e:
            t = list(lam)
            scale = gf_div(delta, bcoef)
            shifted = [0] * m + b
            lam = [
                (lam[j] if j < len(lam) else 0) ^ (gf_mul(scale, shifted[j]) if j < len(shifted) else 0)
                for j in range(max(len(lam), len(shifted)))
            ]
            L = i + 1 + e - L
            b = t
            bcoef = delta
            m = 1
        else:
            scale = gf_div(delta, bcoef)
            shifted = [0] * m + b
            lam = [
                (lam[j] if j < len(lam) else 0) ^ (gf_mul(scale, shifted[j]) if j < len(shifted) else 0)
                for j in range(max(len(lam), len(shifted)))
            ]
            m += 1
    while lam and lam[-1] == 0:
        lam.pop()

    num_errata = len(lam) - 1
    if 2 * (num_errata - e) + e > parity:
        raise RSUncorrectable("beyond budget")

    # Chien search: positions p where Λ(X_p^{-1}) = 0.
    positions = []
    for p in range(n):
        xinv = _EXP[(255 - ((n - 1 - p) % 255)) % 255]
        acc = 0
        xp = 1
        for c in lam:
            acc ^= gf_mul(c, xp)
            xp = gf_mul(xp, xinv)
        if acc == 0:
            positions.append(p)
    if len(positions) != num_errata:
        raise RSUncorrectable("locator degree mismatch")

    # Forney: Ω(x) = S(x)Λ(x) mod x^parity;  e_p = X_p·Ω(X_p^{-1}) / Λ'(X_p^{-1}).
    omega = poly_mul(S, lam)[:parity]
    lam_deriv = [lam[j] for j in range(1, len(lam), 2)]  # formal derivative, char 2
    corrected = bytearray(received)
    for p in positions:
        X = _EXP[(n - 1 - p) % 255]
        xinv = _EXP[(255 - _LOG[X]) % 255]

        def eval_at(poly, x):
            acc = 0
            xp = 1
            for c in poly:
                acc ^= gf_mul(c, xp)
                xp = gf_mul(xp, x)
            return acc

        num = eval_at(omega, xinv)
        # Λ'(x) has only even-power terms removed; evaluate at xinv^2 steps:
        den = 0
        xp = 1
        xinv2 = gf_mul(xinv, xinv)
        for c in lam_deriv:
            den ^= gf_mul(c, xp)
            xp = gf_mul(xp, xinv2)
        if den == 0:
            raise RSUncorrectable("Forney denominator zero")
        corrected[p] ^= gf_mul(X, gf_div(num, den))

    # Verify: recompute syndromes.
    for i in range(parity):
        acc = 0
        a = _EXP[i]
        for byte in corrected:
            acc = gf_mul(acc, a) ^ byte
        if acc != 0:
            raise RSUncorrectable("residual syndrome")
    return bytes(corrected[:k])


# ─────────────────────────────────────────────────────────────────────────────
# §4 Bech32 footer token
# ─────────────────────────────────────────────────────────────────────────────

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
HRP = "cv"  # checksum input only, never printed (spec §4.3)
SENTINEL = "cv0"
DATA_CHARS = 133
TOKEN_LEN = 142
ERASURE = "?"
_GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]


def _polymod(values):
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= _GEN[i]
    return chk


def _hrp_expand(hrp):
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def create_checksum(data):
    mod = _polymod(_hrp_expand(HRP) + list(data) + [0] * 6) ^ 1
    return [(mod >> (5 * (5 - i))) & 31 for i in range(6)]


def verify_checksum(data_with_checksum):
    return _polymod(_hrp_expand(HRP) + list(data_with_checksum)) == 1


def encode_token(codeword: bytes) -> str:
    """83 bytes → 664 bits MSB-first → 133 five-bit values (final char
    right-padded with one 0 bit) + 6-char checksum (spec §4.2–§4.3)."""
    bits = "".join(f"{b:08b}" for b in codeword) + "0"  # 665 bits
    values = [int(bits[i * 5 : i * 5 + 5], 2) for i in range(DATA_CHARS)]
    checksum = create_checksum(values)
    return SENTINEL + "".join(CHARSET[v] for v in values + checksum)


def extract_token(text: str) -> str | None:
    """Structural extraction (spec §4.4): sentinel rule, else length-run
    fallback taking the trailing TOKEN_LEN characters."""
    compact = "".join(c for c in text.lower() if not c.isspace())
    runs, cur = [], ""
    for c in compact + "\x00":
        if c in CHARSET or c == ERASURE:
            cur += c
        else:
            if cur:
                runs.append(cur)
            cur = ""
    for r in runs:
        at = r.find(SENTINEL)
        if at >= 0 and len(r) - at >= TOKEN_LEN:
            return r[at : at + TOKEN_LEN]
    for r in runs:
        if len(r) >= TOKEN_LEN:
            return r[-TOKEN_LEN:]
    return None


def decode_token(text: str) -> dict:
    """Pasted text → dict(capsule, checksum_valid, erasures, extracted)."""
    token = extract_token(text)
    if token is None:
        return {"extracted": False, "capsule": None, "checksum_valid": None, "erasures": 0, "failure": "no token"}
    body = token[len(SENTINEL) :]
    values = [None if c == ERASURE else CHARSET.index(c) for c in body]
    checksum_valid = None
    if all(v is not None for v in values):
        checksum_valid = verify_checksum(values)
    data_values = values[:DATA_CHARS]
    # Rebuild 83 bytes; erased chars → erasures on every overlapped byte.
    bits = ""
    erased = set()
    for idx, v in enumerate(data_values):
        if v is None:
            erased.add((idx * 5) // 8)
            end = (idx * 5 + 4) // 8
            if end < RS_N:
                erased.add(end)
            v = 0
        bits += f"{v:05b}"
    bits = bits[: RS_N * 8]  # drop the single pad bit
    received = bytes(int(bits[i * 8 : i * 8 + 8], 2) for i in range(RS_N))
    try:
        capsule = rs_decode(received, RS_PARITY, sorted(erased))
    except RSUncorrectable as exc:
        return {"extracted": True, "capsule": None, "checksum_valid": checksum_valid,
                "erasures": len(erased), "failure": str(exc)}
    return {"extracted": True, "capsule": capsule, "checksum_valid": checksum_valid,
            "erasures": len(erased), "failure": None}


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline (§1) + fingerprint support for the conformance vector
# ─────────────────────────────────────────────────────────────────────────────

def encode_pipeline(seed_entropy: bytes, vault_key: bytes) -> str:
    return encode_token(rs_encode(create_capsule(seed_entropy, vault_key)))


def decode_pipeline(text: str, vault_key: bytes) -> bytes:
    result = decode_token(text)
    if result["capsule"] is None:
        raise CapsuleError(result["failure"] or "decode failed")
    return open_capsule(result["capsule"], vault_key)


def render_footer_lines(token: str, printed_date: str) -> list[str]:
    """Presentation only (spec §5): 48-char wrap inside fake print exhaust."""
    wrapped = [token[i : i + 48] for i in range(0, len(token), 48)]
    lines = [f"https://arecipeforamaster.com/print?id={wrapped[0]}"] + wrapped[1:]
    lines[-1] += "&v=1"
    lines.append(f"Printed {printed_date} · page 1 of 1")
    return lines


# BIP39/BIP32 fingerprint (standard algorithms; needed to check the vector's
# expected fingerprint). Pure stdlib + pure-Python secp256k1/RIPEMD-160.

def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    m = unicodedata.normalize("NFKD", mnemonic)
    s = unicodedata.normalize("NFKD", "mnemonic" + passphrase)
    return hashlib.pbkdf2_hmac("sha512", m.encode(), s.encode(), 2048, 64)


_P = 2**256 - 2**32 - 977
_N_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def _ec_add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        lam = (3 * a[0] * a[0]) * pow(2 * a[1], _P - 2, _P) % _P
    else:
        lam = (b[1] - a[1]) * pow(b[0] - a[0], _P - 2, _P) % _P
    x = (lam * lam - a[0] - b[0]) % _P
    return (x, (lam * (a[0] - x) - a[1]) % _P)


def _ec_mul(k, point):
    result = None
    addend = point
    while k:
        if k & 1:
            result = _ec_add(result, addend)
        addend = _ec_add(addend, addend)
        k >>= 1
    return result


def _ripemd160(data: bytes) -> bytes:
    try:
        return hashlib.new("ripemd160", data).digest()
    except ValueError:
        return _ripemd160_pure(data)


def _ripemd160_pure(message: bytes) -> bytes:
    # Pure-Python RIPEMD-160 (public standard, ISO/IEC 10118-3).
    def rol(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    r1 = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,
          3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,
          4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13]
    r2 = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,
          15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,
          12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11]
    s1 = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,
          11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,
          9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6]
    s2 = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,
          9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,
          8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11]
    K1 = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
    K2 = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]

    def f(j, x, y, z):
        if j < 16:
            return x ^ y ^ z
        if j < 32:
            return (x & y) | (~x & z)
        if j < 48:
            return (x | ~y) ^ z
        if j < 64:
            return (x & z) | (y & ~z)
        return x ^ (y | ~z)

    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    ml = len(message)
    message += b"\x80" + b"\x00" * ((55 - ml) % 64) + (8 * ml).to_bytes(8, "little")
    for off in range(0, len(message), 64):
        x = [int.from_bytes(message[off + 4 * i : off + 4 * i + 4], "little") for i in range(16)]
        a1, b1, c1, d1, e1 = h
        a2, b2, c2, d2, e2 = h
        for j in range(80):
            t = (rol((a1 + f(j, b1, c1, d1) + x[r1[j]] + K1[j // 16]) & 0xFFFFFFFF, s1[j]) + e1) & 0xFFFFFFFF
            a1, e1, d1, c1, b1 = e1, d1, rol(c1, 10), b1, t
            t = (rol((a2 + f(79 - j, b2, c2, d2) + x[r2[j]] + K2[j // 16]) & 0xFFFFFFFF, s2[j]) + e2) & 0xFFFFFFFF
            a2, e2, d2, c2, b2 = e2, d2, rol(c2, 10), b2, t
        t = (h[1] + c1 + d2) & 0xFFFFFFFF
        h = [t, (h[2] + d1 + e2) & 0xFFFFFFFF, (h[3] + e1 + a2) & 0xFFFFFFFF,
             (h[4] + a1 + b2) & 0xFFFFFFFF, (h[0] + b1 + c2) & 0xFFFFFFFF]
    return b"".join(v.to_bytes(4, "little") for v in h)


def master_fingerprint(mnemonic: str) -> str:
    seed = mnemonic_to_seed(mnemonic)
    digest = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    k = int.from_bytes(digest[:32], "big")
    if not (0 < k < _N_ORDER):
        raise ValueError("invalid master key")
    px, py = _ec_mul(k, _G)
    pubkey = bytes([2 + (py & 1)]) + px.to_bytes(32, "big")
    fp = _ripemd160(hashlib.sha256(pubkey).digest())[:4]
    h = fp.hex().upper()
    return f"{h[:4]}-{h[4:]}"
