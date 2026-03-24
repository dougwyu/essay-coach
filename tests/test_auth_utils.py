from auth import hash_password, verify_password, generate_token, generate_invite_code, compare_codes


def test_hash_and_verify_correct_password():
    h = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", h) is True


def test_verify_wrong_password():
    h = hash_password("secret")
    assert verify_password("wrong", h) is False


def test_generate_token_is_64_hex_chars():
    token = generate_token()
    assert len(token) == 64
    assert all(c in "0123456789abcdef" for c in token)


def test_generate_token_is_unique():
    assert generate_token() != generate_token()


def test_generate_invite_code_length_and_charset():
    code = generate_invite_code()
    assert len(code) == 8
    valid = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    assert all(c in valid for c in code)


def test_compare_codes_match():
    assert compare_codes("ABC123XY", "ABC123XY") is True


def test_compare_codes_no_match():
    assert compare_codes("ABC123XY", "XY123ABC") is False
