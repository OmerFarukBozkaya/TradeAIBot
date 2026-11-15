from app.security import hash_password, verify_password


def test_password_hash_roundtrip():
    encoded = hash_password("CokGizli123!")
    assert encoded.startswith("scrypt$")
    assert verify_password("CokGizli123!", encoded)
    assert not verify_password("yanlis", encoded)


def test_hash_is_salted():
    assert hash_password("ayni") != hash_password("ayni")
