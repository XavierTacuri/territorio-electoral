from datetime import timedelta
from uuid import uuid4
import jwt
import pytest
from app.core.config import settings
from app.core.security import TokenValidationError, create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_and_verify():
    first, second = hash_password("Secure123"), hash_password("Secure123")
    assert first != second
    assert verify_password("Secure123", first)
    assert not verify_password("Wrong123", first)
    assert "Secure123" not in first

@pytest.mark.parametrize("password", ["short1", "onlyletters", "12345678"])
def test_invalid_password(password):
    with pytest.raises(ValueError): hash_password(password)


def test_jwt_round_trip():
    subject = uuid4(); payload = decode_access_token(create_access_token(subject))
    assert payload["sub"] == str(subject) and payload["type"] == "access"


def test_expired_token():
    token = create_access_token(uuid4(), timedelta(seconds=-1))
    with pytest.raises(TokenValidationError): decode_access_token(token)


def test_tampered_token():
    token = create_access_token(uuid4()) + "x"
    with pytest.raises(TokenValidationError): decode_access_token(token)


def test_wrong_token_type():
    token = jwt.encode({"sub": str(uuid4()), "type": "refresh", "iat": 1, "exp": 4102444800}, settings.secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenValidationError): decode_access_token(token)
