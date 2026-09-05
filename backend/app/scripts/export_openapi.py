"""Exporta el esquema OpenAPI directamente desde la app FastAPI (fuente de verdad).

frontend/openapi.json es una instantánea de este esquema; el pipeline
correcto para actualizarlo es ejecutar este script y regenerar el cliente
(`npm run api:generate` en frontend), nunca editar el cliente generado a mano.
"""
import json
import sys

from app.main import app


def main():
    schema = app.openapi()
    text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False)
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
