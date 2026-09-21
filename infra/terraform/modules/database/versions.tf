terraform {
  # >= 1.11.0, no >= 1.7.0 como el resto de la fundacion (network/security_groups/
  # alb/ecs): este modulo usa `ephemeral "random_password"` (recursos
  # ephemeral, Terraform >= 1.10) y `secret_string_wo`/`secret_string_wo_version`
  # (argumentos write-only, Terraform >= 1.11) en aws_secretsmanager_secret_version
  # — ver main.tf, "Usuario de APLICACION". Terraform aplica el maximo de los
  # required_version de todos los modulos de la configuracion, asi que este
  # bloque ya eleva el minimo efectivo de todo `environments/prod`.
  required_version = ">= 1.11.0, < 2.0.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # >= 5.27 ya cubria el resto del modulo; secret_string_wo/secret_string_wo_version
      # en aws_secretsmanager_secret_version estan disponibles en la version
      # 5.100.0 ya resuelta (confirmado con `terraform providers schema -json`,
      # no asumido) — sin necesidad de subir este piso.
      version = ">= 5.27.0, < 6.0.0"
    }
    # Genera la contrasenia del usuario de APLICACION (nunca la del usuario
    # maestro, que administra RDS via manage_master_user_password — ver
    # main.tf) como recurso `ephemeral`, no `resource`: el valor generado
    # nunca se persiste en el state de Terraform. La version 3.9.1 ya
    # resuelta soporta `ephemeral "random_password"` (confirmado con
    # `terraform providers schema -json`) — sin necesidad de subir este piso.
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6.0, < 4.0.0"
    }
  }
}
