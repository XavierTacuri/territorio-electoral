terraform {
  # >= 1.11.0, no >= 1.7.0 como la mayoria de la fundacion: este modulo usa
  # `ephemeral "random_password"` (recursos ephemeral, Terraform >= 1.10) y
  # `secret_string_wo`/`secret_string_wo_version` (argumentos write-only,
  # Terraform >= 1.11) en aws_secretsmanager_secret_version — mismo patron
  # que modules/database ya usa para el password del usuario de aplicacion.
  # Terraform aplica el maximo de los required_version de todos los modulos
  # de la configuracion, asi que este piso no eleva nada que
  # modules/database no elevara ya.
  required_version = ">= 1.11.0, < 2.0.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # secret_string_wo/secret_string_wo_version en
      # aws_secretsmanager_secret_version confirmados disponibles en la
      # version 5.100.0 ya resuelta (`terraform providers schema -json`,
      # no asumido) — sin necesidad de subir este piso.
      version = ">= 5.27.0, < 6.0.0"
    }
    # ephemeral "random_password" confirmado disponible en la version 3.9.1
    # ya resuelta (`terraform providers schema -json`, no asumido).
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6.0, < 4.0.0"
    }
  }
}
