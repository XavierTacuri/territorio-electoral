# ============================================================================
# DB subnet group — exclusivamente subredes privadas de base de datos (4C.1)
# ============================================================================

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.db_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-subnet-group" })
}

# ============================================================================
# RDS PostgreSQL
# ============================================================================
# Sin custom parameter group (item 28): la configuracion por defecto del
# parameter group de la familia postgres16 es suficiente para esta fase — no
# existe todavia ninguna necesidad de tuning concreta que la justifique.
# Sin enhanced monitoring (item 27): requeriria un IAM role adicional
# dedicado solo para eso; Performance Insights (sin ese requisito) ya cubre
# diagnostico de queries si se habilita, sin coste obligatorio por defecto.

resource "aws_db_instance" "this" {
  identifier = "${var.name_prefix}-db"

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  # Nunca desactivable en esta fase (item 24) — no es una variable a proposito.
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  # RDS genera y administra la contrasenia maestra en un secreto de Secrets
  # Manager propio — Terraform nunca ve, calcula ni almacena el valor en
  # texto plano (ni en el codigo ni en el state). Ver docs/aws/RDS_PROXY_FOUNDATION.md,
  # "Manejo de credenciales".
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.rds_security_group_id]
  # Invariante de seguridad, no una variable a proposito (item 6 de Fase 4C.3
  # / criterios de aceptacion): esta base de datos nunca debe ser accesible
  # desde Internet.
  publicly_accessible = false
  port                = var.db_port

  multi_az = var.multi_az

  backup_retention_period = var.backup_retention_period
  backup_window           = var.backup_window
  maintenance_window      = var.maintenance_window
  copy_tags_to_snapshot   = var.copy_tags_to_snapshot

  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot
  # Identificador ESTABLE (sin timestamp()) — timestamp() en un
  # final_snapshot_identifier produciria un diff de Terraform en cada plan,
  # incluso sin cambios reales. Si esta instancia llegara a eliminarse y
  # recrearse bajo el mismo name_prefix, un segundo snapshot con este mismo
  # nombre chocaria con el primero — caso extremo documentado, no resuelto
  # con complejidad adicional aqui (ver docs/aws/RDS_PROXY_FOUNDATION.md).
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name_prefix}-db-final-snapshot"

  performance_insights_enabled = var.performance_insights_enabled

  apply_immediately = var.apply_immediately

  tags = merge(var.tags, { Name = "${var.name_prefix}-db" })
}

# ============================================================================
# Usuario de APLICACION — secreto propio, generado por Terraform
# ============================================================================
# El rol de Postgres en si (CREATE ROLE + GRANTs de minimo privilegio, sin
# CREATEROLE/CREATEDB/rds_superuser) lo crea/actualiza la task de bootstrap
# de modulos/ecs (usa las credenciales del usuario MAESTRO para poder
# ejecutar CREATE ROLE) — este modulo solo genera y guarda el secreto que
# ese rol usara como contrasenia. A diferencia del usuario maestro
# (manage_master_user_password = true, gestionado integramente por AWS), no
# existe un mecanismo nativo de RDS para generar automaticamente la
# contrasenia de un rol de aplicacion arbitrario.
#
# `ephemeral "random_password"` (no `resource`) + `secret_string_wo` (no
# `secret_string`) en aws_secretsmanager_secret_version de abajo: verificado
# contra el schema real de los providers ya resueltos (`terraform providers
# schema -json`, hashicorp/random 3.9.1 y hashicorp/aws 5.100.0 — ambos ya
# soportan esto, sin necesidad de subir ninguna version). Un recurso
# `ephemeral` nunca persiste su resultado en el state de Terraform (esa es
# su definicion); un argumento write-only (`secret_string_wo`) nunca se lee
# de vuelta ni se guarda en el state — la unica huella que Terraform
# conserva es `secret_string_wo_version` (un numero, no el valor), que es
# lo que decide SI reescribir el secreto, no QUE valor escribir. Resultado:
# la contrasenia del usuario de aplicacion no queda en el state de
# Terraform, a diferencia de la version anterior de este modulo
# (`resource "random_password"`, cuyo `.result` SI persistia en el state).
ephemeral "random_password" "app_user" {
  length  = 32
  special = true
}

resource "aws_secretsmanager_secret" "app_user" {
  name        = "${var.name_prefix}-db-app-user"
  description = "Credenciales del usuario de aplicacion de PostgreSQL (bajo privilegio) — usado por el ECS backend en runtime, via RDS Proxy."

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-app-user" })
}

resource "aws_secretsmanager_secret_version" "app_user" {
  secret_id = aws_secretsmanager_secret.app_user.id
  # Misma forma JSON {"username":"...","password":"..."} que el secreto
  # gestionado por RDS para el usuario maestro — consistencia deliberada:
  # ambos se consumen desde ECS con el mismo sufijo ":password::". El valor
  # completo (incluido el password efimero) fluye por el argumento
  # write-only — nunca por `secret_string`.
  secret_string_wo = jsonencode({
    username = var.db_app_username
    password = ephemeral.random_password.app_user.result
  })
  # Controla CUANDO se reescribe el secreto: Terraform no puede diferenciar
  # un valor write-only "nuevo" de uno "sin cambios" (nunca retiene el
  # anterior para comparar) — por eso el disparador es este numero, no el
  # contenido. Mientras var.db_app_secret_version no cambie entre applies,
  # el secreto NO se reescribe (aunque el `ephemeral.random_password` de
  # arriba genere tecnicamente un valor distinto en cada evaluacion, ese
  # valor nuevo nunca llega a AWS). Rotacion (manual, no automatizada en
  # esta fase): incrementar var.db_app_secret_version + `terraform apply` +
  # volver a invocar la bootstrap task (aws_ecs_task_definition.backend_bootstrap,
  # modulo ecs) para que `ALTER ROLE ... PASSWORD` sincronice el rol de
  # PostgreSQL con el nuevo valor del secreto — dos pasos deliberadamente
  # manuales y separados, no un pipeline automatico. Ver docs/aws/RDS_PROXY_FOUNDATION.md,
  # "Rotacion futura".
  secret_string_wo_version = var.db_app_secret_version
}

# ============================================================================
# IAM para RDS Proxy — solo puede leer los dos secretos que realmente
# necesita (maestro + aplicacion), nunca un wildcard.
# ============================================================================

data "aws_iam_policy_document" "rds_proxy_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "proxy" {
  name               = "${var.name_prefix}-rds-proxy"
  assume_role_policy = data.aws_iam_policy_document.rds_proxy_assume_role.json

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-proxy" })
}

resource "aws_iam_role_policy" "proxy_secrets" {
  name = "${var.name_prefix}-rds-proxy-secrets"
  role = aws_iam_role.proxy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_db_instance.this.master_user_secret[0].secret_arn,
        aws_secretsmanager_secret.app_user.arn,
      ]
    }]
  })
}

# ============================================================================
# RDS Proxy
# ============================================================================
# Dos identidades autenticables, nunca mas: el usuario maestro (solo lo usan
# las tasks de bootstrap/migracion, nunca el ECS Service del backend) y el
# usuario de aplicacion (el que SI usa el ECS Service en runtime). RDS Proxy
# elige el secreto correcto segun el username que presenta cada conexion
# entrante — "el proxy debe autenticar unicamente los usuarios que
# realmente necesiten conectarse a traves de el" (item 4).

resource "aws_db_proxy" "this" {
  name                   = "${var.name_prefix}-proxy"
  engine_family          = "POSTGRESQL"
  role_arn               = aws_iam_role.proxy.arn
  vpc_subnet_ids         = var.db_subnet_ids
  vpc_security_group_ids = [var.rds_proxy_security_group_id]
  require_tls            = var.require_tls
  idle_client_timeout    = var.idle_client_timeout
  # publicly_accessible no existe como argumento configurable en
  # aws_db_proxy — RDS Proxy nunca es publicamente accesible por diseño de
  # la API de AWS cuando se crea dentro de una VPC privada como esta.

  auth {
    description = "Usuario maestro — solo bootstrap y migration task (Alembic)."
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_db_instance.this.master_user_secret[0].secret_arn
  }

  auth {
    description = "Usuario de aplicacion — ECS backend Service en runtime."
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.app_user.arn
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-proxy" })
}

resource "aws_db_proxy_default_target_group" "this" {
  db_proxy_name = aws_db_proxy.this.name

  connection_pool_config {
    connection_borrow_timeout    = var.connection_borrow_timeout
    max_connections_percent      = var.max_connections_percent
    max_idle_connections_percent = var.max_idle_connections_percent
  }
}

resource "aws_db_proxy_target" "this" {
  db_proxy_name          = aws_db_proxy.this.name
  target_group_name      = aws_db_proxy_default_target_group.this.name
  db_instance_identifier = aws_db_instance.this.identifier
}
