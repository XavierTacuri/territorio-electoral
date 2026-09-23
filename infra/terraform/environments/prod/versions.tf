terraform {
  # >= 1.7.0 es el piso propio de este archivo; el piso EFECTIVO de todo el
  # stack es >= 1.11.0 porque modules/database declara ese requisito (usa
  # recursos ephemeral y argumentos write-only, Fase 4C.3) — Terraform
  # aplica el maximo de los required_version de todos los modulos de la
  # configuracion. No se sube este valor a mano para no duplicar una
  # constraint que ya vive, correctamente, en el modulo que realmente la
  # necesita.
  required_version = ">= 1.7.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.27.0, < 6.0.0"
    }
  }

  # Backend "s3" con configuracion PARCIAL (Fase 4D.1) — el bloque va vacio
  # a proposito: bucket/key/region/use_lockfile se pasan en `terraform init`
  # via `-backend-config`, nunca hardcodeados aqui (sin nombre de bucket
  # real, account ID ni credenciales en el repo). Ver
  # docs/aws/AWS_BOOTSTRAP.md, "Migracion del backend", para el
  # procedimiento completo — NO ejecutado todavia.
  #
  # Mientras el bucket de docs/aws/AWS_BOOTSTRAP.md no exista realmente en
  # AWS, `terraform init -backend=false` sigue siendo la unica forma valida
  # de validar este stack localmente (ver infra/terraform/README.md): con
  # `-backend=false` Terraform ignora por completo este bloque, incluso
  # vacio, y no intenta contactar AWS ni requiere `-backend-config`.
  backend "s3" {}
}
