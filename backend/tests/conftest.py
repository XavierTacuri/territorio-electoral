from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.role_service import RoleService

@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        RoleService(session).initialize_roles(); session.commit()
        yield session
    Base.metadata.drop_all(engine)

@pytest.fixture
def admin(db: Session) -> User:
    role = RoleService(db).repository.get_by_code("ADMIN")
    user = User(email="admin@example.com", username="admin", first_name="Admin", last_name="Test", hashed_password=hash_password("AdminPass123"), is_active=True, is_superuser=True, roles=[role])
    db.add(user); db.commit(); db.refresh(user); return user

@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_db(): yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client: yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def admin_headers(client: TestClient, admin: User) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", data={"username": "admin", "password": "AdminPass123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
