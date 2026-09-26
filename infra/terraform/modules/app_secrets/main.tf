# Genera y administra los 4 secretos de aplicacion que backend/app/core/config.py
# exige explicitamente en app_env=production (ver validate_security_settings):
# SECRET_KEY, BROWSER_REFRESH_TOKEN_HMAC_SECRET, SURVEY_SUBMISSION_HMAC_SECRET,
# INITIAL_ADMIN_PASSWORD — ninguno tenia infraestructura propia hasta ahora
# (secrets_manager_secret_arns era un mapa vacio que el operador debia llenar
# a mano, fuera de Terraform). Mismo mecanismo YA verificado y en uso en
# modules/database para el password del usuario de aplicacion de PostgreSQL:
# `ephemeral "random_password"` (nunca `resource`) + `secret_string_wo`
# (nunca `secret_string`) en aws_secretsmanager_secret_version — ningun
# valor generado por este modulo llega jamas al state de Terraform. La unica
# huella que el state conserva es `secret_string_wo_version` (un numero),
# que decide SI reescribir el secreto, nunca QUE valor escribir.
#
# SECRET_KEY/BROWSER_REFRESH_TOKEN_HMAC_SECRET: backend/app/core/config.py
# exige >=32 caracteres en produccion — se generan con 64 para dejar margen.
# SURVEY_SUBMISSION_HMAC_SECRET: sin longitud minima explicita en el codigo,
# mismo criterio conservador (48). INITIAL_ADMIN_PASSWORD: password real de
# un usuario (no un secreto criptografico) — 32 caracteres con simbolos es
# una longitud robusta tipica.
locals {
  secrets = {
    SECRET_KEY                        = { length = 64 }
    BROWSER_REFRESH_TOKEN_HMAC_SECRET = { length = 64 }
    SURVEY_SUBMISSION_HMAC_SECRET     = { length = 48 }
    INITIAL_ADMIN_PASSWORD            = { length = 32 }
  }
}

ephemeral "random_password" "this" {
  for_each = local.secrets

  length  = each.value.length
  special = true
}

resource "aws_secretsmanager_secret" "this" {
  for_each = local.secrets

  name        = "${var.name_prefix}-app-${lower(replace(each.key, "_", "-"))}"
  description = "Valor de ${each.key}, generado aleatoriamente y administrado por Terraform (ephemeral + write-only — nunca persiste en tfstate). Consumido por module.ecs via secrets_manager_secret_arns."

  tags = merge(var.tags, { Name = "${var.name_prefix}-app-${lower(replace(each.key, "_", "-"))}" })
}

resource "aws_secretsmanager_secret_version" "this" {
  for_each = local.secrets

  secret_id = aws_secretsmanager_secret.this[each.key].id
  # Valor plano (no JSON): a diferencia de POSTGRES_PASSWORD (que comparte
  # secreto con "username" y se extrae con sufijo ":password::"), ECS
  # inyecta estos 4 directo como `valueFrom = <arn>` sin sufijo — el
  # `secrets_string_wo` completo ES el valor de la variable de entorno.
  secret_string_wo         = ephemeral.random_password.this[each.key].result
  secret_string_wo_version = var.secret_version
}
