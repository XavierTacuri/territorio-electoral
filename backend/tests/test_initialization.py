from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.role import Role
from app.models.user import User
from app.scripts import create_admin
from app.services.role_service import RoleService


def test_initial_roles_are_idempotent(db: Session):
    RoleService(db).initialize_roles(); RoleService(db).initialize_roles(); db.commit()
    assert db.scalar(select(func.count()).select_from(Role)) == 5


def test_admin_creation_is_idempotent_and_repairs_role(db: Session, monkeypatch):
    monkeypatch.setattr(create_admin, "SessionLocal", lambda: db)
    create_admin.create_initial_admin(); create_admin.create_initial_admin()
    users = list(db.scalars(select(User)).all())
    assert len(users) == 1 and users[0].is_superuser
    assert {role.code for role in users[0].roles} == {"ADMIN"}


def test_existing_user_receives_admin_role(db: Session, monkeypatch):
    user = User(email="admin@example.com", username="admin", first_name="Existing", last_name="User", hashed_password="existing-hash", roles=[])
    db.add(user); db.commit()
    monkeypatch.setattr(create_admin, "SessionLocal", lambda: db)
    create_admin.create_initial_admin()
    assert user.is_superuser and user.is_active and "ADMIN" in {role.code for role in user.roles}
    assert user.hashed_password == "existing-hash"
