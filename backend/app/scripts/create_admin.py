from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.services.role_service import RoleService


def create_initial_admin() -> None:
    with SessionLocal() as db:
        try:
            RoleService(db).initialize_roles()
            users = UserRepository(db)
            user = users.get_by_email(settings.initial_admin_email) or users.get_by_username(settings.initial_admin_username)
            admin_role = RoleService(db).repository.get_by_code("ADMIN")
            if user is None:
                user = users.create(email=settings.initial_admin_email, username=settings.initial_admin_username, first_name=settings.initial_admin_first_name.strip(), last_name=settings.initial_admin_last_name.strip(), hashed_password=hash_password(settings.initial_admin_password), is_active=True, is_superuser=True, roles=[admin_role])
                db.commit()
                print("Administrador inicial creado correctamente.")
            else:
                if admin_role not in user.roles: user.roles.append(admin_role)
                user.is_superuser = True; user.is_active = True
                db.commit()
                print("El administrador inicial ya existía; permisos verificados.")
        except (SQLAlchemyError, ValueError):
            db.rollback()
            print("No fue posible crear el administrador inicial.")
            raise SystemExit(1)


if __name__ == "__main__": create_initial_admin()
