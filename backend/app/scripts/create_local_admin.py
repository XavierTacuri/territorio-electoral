from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_local_development_password
from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.services.role_service import RoleService


def create_local_admin() -> None:
    if settings.app_env.lower() != "development":
        raise SystemExit("Este script solo puede ejecutarse con APP_ENV=development.")

    with SessionLocal() as db:
        try:
            roles = RoleService(db)
            roles.initialize_roles()
            admin_role = roles.repository.get_by_code("ADMIN")
            if admin_role is None:
                raise RuntimeError("No fue posible inicializar el rol ADMIN")

            users = UserRepository(db)
            user = users.get_by_username("admin")
            email_owner = users.get_by_email("admin@territorio.local")
            if user is None and email_owner is not None:
                raise RuntimeError("El email local ya pertenece a otro usuario")

            password_hash = hash_local_development_password("admin")
            if user is None:
                user = users.create(
                    email="admin@territorio.local",
                    username="admin",
                    first_name="Administrador",
                    last_name="Sistema",
                    hashed_password=password_hash,
                    is_active=True,
                    is_superuser=True,
                    roles=[admin_role],
                )
                message = "Administrador local creado correctamente."
            else:
                user.email = "admin@territorio.local"
                user.first_name = "Administrador"
                user.last_name = "Sistema"
                user.hashed_password = password_hash
                user.is_active = True
                user.is_superuser = True
                if admin_role not in user.roles:
                    user.roles.append(admin_role)
                message = "Administrador local actualizado correctamente."

            db.commit()
            print(message)
        except (SQLAlchemyError, RuntimeError, ValueError):
            db.rollback()
            print("No fue posible configurar el administrador local.")
            raise SystemExit(1)


if __name__ == "__main__":
    create_local_admin()
