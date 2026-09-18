import re
import time

from remotepad_server import session as session_mod


def test_generate_pin_is_six_digits() -> None:
    for _ in range(50):
        pin = session_mod.generate_pin()
        assert re.fullmatch(r"\d{6}", pin)


def test_derive_token_is_deterministic() -> None:
    nonce_s = b"\x01" * 16
    nonce_c = b"\x02" * 16
    token_a = session_mod.derive_token("123456", nonce_s, nonce_c)
    token_b = session_mod.derive_token("123456", nonce_s, nonce_c)
    assert token_a == token_b
    assert len(token_a) == 32


def test_derive_token_differs_with_different_pin() -> None:
    nonce_s = b"\x01" * 16
    nonce_c = b"\x02" * 16
    token_a = session_mod.derive_token("123456", nonce_s, nonce_c)
    token_b = session_mod.derive_token("654321", nonce_s, nonce_c)
    assert token_a != token_b


def test_compute_pair_proof_matches_same_inputs() -> None:
    nonce_s, nonce_c = b"s" * 16, b"c" * 16
    a = session_mod.compute_pair_proof("111111", nonce_s, nonce_c)
    b = session_mod.compute_pair_proof("111111", nonce_s, nonce_c)
    assert a == b


def test_compute_message_sig_is_16_hex_chars() -> None:
    token = bytes(range(32))
    sig = session_mod.compute_message_sig(token, "session-1", "msg-1", "ping")
    assert len(sig) == 16
    int(sig, 16)  # no debe lanzar: es hex válido


def test_pairing_challenge_expiry() -> None:
    challenge = session_mod.PairingChallenge(
        client_id="c", client_name="n", pin="000000", nonce_server=b"s", nonce_client=b"c"
    )
    assert not challenge.is_expired(now=challenge.created_at + 1)
    assert challenge.is_expired(now=challenge.created_at + session_mod.PAIR_TTL_SECONDS + 1)


def test_lockout_after_max_attempts() -> None:
    lockout = session_mod.LockoutState()
    now = time.monotonic()
    for _ in range(session_mod.MAX_PAIR_ATTEMPTS - 1):
        lockout.register_failure(now=now)
        assert not lockout.is_locked(now=now)
    lockout.register_failure(now=now)
    assert lockout.is_locked(now=now)
    assert not lockout.is_locked(now=now + session_mod.LOCKOUT_SECONDS + 1)


def test_lockout_reset() -> None:
    lockout = session_mod.LockoutState()
    lockout.register_failure()
    lockout.reset()
    assert lockout.attempts == 0
    assert not lockout.is_locked()


def test_active_session_ping_staleness() -> None:
    active = session_mod.ActiveSession(session_id="s", client_id="c", token=b"\x00" * 32)
    now = active.last_ping
    assert not active.is_ping_stale(now=now + 1, timeout=10)
    assert active.is_ping_stale(now=now + 11, timeout=10)
    active.touch_ping(now=now + 11)
    assert not active.is_ping_stale(now=now + 12, timeout=10)
