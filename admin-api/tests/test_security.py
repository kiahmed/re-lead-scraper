from core import security


def test_hash_and_verify_roundtrip():
    stored = security.hash_password("hunter22")
    assert stored.startswith("scrypt$")
    assert security.verify_password("hunter22", stored)
    assert not security.verify_password("hunter23", stored)


def test_hashes_are_salted():
    assert security.hash_password("same") != security.hash_password("same")


def test_verify_garbage_is_false_not_exception():
    assert not security.verify_password("x", "")
    assert not security.verify_password("x", "plaintext")
    assert not security.verify_password("x", "bcrypt$whatever$else$here$a$b")


def test_token_hash_is_stable_and_hex():
    token = security.new_token()
    assert len(token) >= 40
    assert security.token_hash(token) == security.token_hash(token)
    assert len(security.token_hash(token)) == 64
