import pytest

from app.core.security import hash_password
from app.models.user import User
from app.services.campaign_permissions import has_campaign_executive_role
from app.services.role_service import RoleService


@pytest.mark.parametrize("role_code", ["CANDIDATE", "CAMPAIGN_MANAGER"])
def test_campaign_executive_roles_share_capability_group(db, role_code):
    role = RoleService(db).repository.get_by_code(role_code)
    user = User(
        email=f"{role_code.lower()}-parity@example.test",
        username=f"{role_code.lower()}-parity",
        first_name="Parity",
        last_name="Test",
        hashed_password=hash_password("Testing123"),
        roles=[role],
    )
    assert has_campaign_executive_role(user)


def test_non_executive_role_is_not_campaign_executive(db):
    role = RoleService(db).repository.get_by_code("ANALYST")
    user = User(
        email="analyst-parity@example.test",
        username="analyst-parity",
        first_name="Analyst",
        last_name="Test",
        hashed_password=hash_password("Testing123"),
        roles=[role],
    )
    assert not has_campaign_executive_role(user)
