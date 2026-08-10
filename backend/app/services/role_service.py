from sqlalchemy.orm import Session
from app.models.role import Role
from app.repositories.role_repository import RoleRepository
from app.services.exceptions import BusinessRuleError

INITIAL_ROLES = (
    ("ADMIN", "Administrador", "Administración completa del sistema"),
    ("CANDIDATE", "Candidato", "Candidato de una campaña"),
    ("CAMPAIGN_MANAGER", "Director de campaña", "Dirección operativa de campaña"),
    ("TERRITORIAL_COORDINATOR", "Coordinador territorial", "Coordinación territorial"),
    ("ANALYST", "Analista", "Análisis de información"),
)


class RoleService:
    def __init__(self, db: Session): self.db, self.repository = db, RoleRepository(db)
    def initialize_roles(self) -> list[Role]:
        roles = []
        for code, name, description in INITIAL_ROLES:
            role = self.repository.get_by_code(code) or self.repository.create(code, name, description)
            roles.append(role)
        self.db.flush()
        return roles
    def get_active_roles(self, codes: list[str]) -> list[Role]:
        normalized = list(dict.fromkeys(c.strip().upper() for c in codes))
        roles = self.repository.get_by_codes(normalized)
        found = {r.code for r in roles}
        missing = [c for c in normalized if c not in found]
        if missing: raise BusinessRuleError(f"Rol inexistente: {missing[0]}")
        inactive = next((r.code for r in roles if not r.is_active), None)
        if inactive: raise BusinessRuleError(f"Rol inactivo: {inactive}")
        return roles
