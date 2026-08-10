from sqlalchemy import Text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import UserDefinedType


class SpatialGeometry(UserDefinedType):
    cache_ok = True
    def __init__(self, geometry_type: str, srid: int = 4326): self.geometry_type, self.srid = geometry_type, srid
    def get_col_spec(self, **kw: object) -> str: return f"geometry({self.geometry_type},{self.srid})"


@compiles(SpatialGeometry, "sqlite")
def compile_sqlite(_type: SpatialGeometry, _compiler: object, **kw: object) -> str:
    return "TEXT"
