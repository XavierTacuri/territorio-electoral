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

  # Backend intencionalmente sin configurar en Fase 4C.1: sin un bloque
  # `backend` aqui, Terraform usa el backend local por defecto, por lo que
  # `terraform init` (con o sin -backend=false) funciona sin credenciales
  # de AWS ni un bucket de state preexistente. Ver
  # docs/aws/TERRAFORM_FOUNDATION.md, seccion "Terraform state", para la
  # estrategia recomendada (S3 + locking nativo) antes de cualquier
  # `terraform apply` real contra AWS.
}
