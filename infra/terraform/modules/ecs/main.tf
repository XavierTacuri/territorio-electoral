# ============================================================================
# Cluster
# ============================================================================

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  # Configurable desde Fase 4C.4 (antes fijo en "disabled" en 4C.2). "enabled"
  # es el valor estandar y bien establecido de Container Insights (agrega
  # metricas por-tarea granulares — RunningTaskCount, PendingTaskCount, etc.
  # bajo el namespace ECS/ContainerInsights — y logs de rendimiento, con
  # costo propio). AWS tambien ofrece un modo "enhanced" (Container Insights
  # with Enhanced Observability) mas reciente; no se usa aqui por no poder
  # verificar con certeza su nombre/comportamiento exacto en este entorno
  # sin acceso a documentacion/consola de AWS — "enabled" es el valor
  # ampliamente documentado y verificable. Deshabilitado por defecto, ver
  # docs/aws/WAF_CLOUDWATCH_FOUNDATION.md, "Costos".
  setting {
    name  = "containerInsights"
    value = var.container_insights_enabled ? "enabled" : "disabled"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cluster" })
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  # Solo Fargate — nunca EC2-backed ECS (item 5). FARGATE_SPOT queda
  # registrado como capacidad disponible pero el peso por defecto de cada
  # servicio es 100% FARGATE on-demand (var.fargate_spot_weight_percent = 0);
  # Spot nunca es la unica capacidad de un servicio.
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 0
  }
}

# ============================================================================
# IAM — Task Execution Role vs. Application Task Role (item 6/7)
# ============================================================================
# Revision de produccion (Fase 4C.7): el frontend (nginx estatico) compartia
# tanto el Execution Role como el Task Role con la familia backend
# (backend/backend_migrate/backend_bootstrap). El Task Role compartido le
# daba al frontend permisos S3 que nunca invoca (nginx no ejecuta AWS SDK);
# el Execution Role compartido le daba, en la definicion de la policy, acceso
# a secretsmanager:GetSecretValue sobre los secretos de DB, aunque la Task
# Definition del frontend nunca declara un bloque `secrets` que lo ejercite.
# Ambos se separan aqui por servicio — minimo privilegio real, no solo por
# ausencia de uso.

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution Role de la familia BACKEND (service, migrate, bootstrap): lo que
# ECS necesita para ARRANCAR esos contenedores (pull de imagen, escribir
# logs, y leer los secretos de DB que sus Task Definitions si declaran) —
# nunca usado por el codigo de la aplicacion en si. El frontend tiene su
# propio Execution Role, mas abajo, sin acceso a estos secretos.
resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-ecs-backend-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-backend-execution" })
}

# Politica administrada por AWS (no es un ARN especifico de este proyecto):
# ecr:GetAuthorizationToken/BatchGetImage/... + logs:CreateLogStream/PutLogEvents.
# Exactamente lo que item 6 pide, nada mas.
resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Permiso para leer exactamente los secretos que las Task Definitions de la
# familia backend referencian en su bloque `secrets` — nunca un wildcard.
# Desde Fase 4C.3, db_master_secret_arn/db_app_secret_arn son obligatorios
# (todo container de la familia backend usa uno de los dos);
# secrets_manager_secret_arns sigue siendo opcional (SECRET_KEY, etc., sin
# infraestructura propia todavia). El frontend nunca recibe este permiso —
# ver aws_iam_role.frontend_execution mas abajo.
resource "aws_iam_role_policy" "execution_secrets" {
  name = "${var.name_prefix}-ecs-backend-execution-secrets"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = concat(
        [var.db_master_secret_arn, var.db_app_secret_arn],
        values(var.secrets_manager_secret_arns),
      )
    }]
  })
}

# Execution Role del FRONTEND: separado del de la familia backend a
# proposito (Fase 4C.7) — el frontend (nginx estatico) nunca declara un
# bloque `secrets` en su Task Definition (su configuracion se hornea en la
# imagen en build time), por lo que no necesita, y no debe poder, leer los
# secretos de DB/aplicacion. Solo la politica administrada de AWS para
# arrancar el contenedor (pull de imagen ECR, logs) — nada de
# secretsmanager:GetSecretValue.
resource "aws_iam_role" "frontend_execution" {
  name               = "${var.name_prefix}-ecs-frontend-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-frontend-execution" })
}

resource "aws_iam_role_policy_attachment" "frontend_execution_managed" {
  role       = aws_iam_role.frontend_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task Role de la familia BACKEND (service, migrate, bootstrap): lo que el
# CODIGO de la aplicacion puede hacer contra APIs de AWS en tiempo de
# ejecucion (boto3 credential provider chain, Fase 4A) — nunca usado por ECS
# para arrancar el contenedor. El frontend (nginx estatico) no ejecuta AWS
# SDK y no recibe ningun Task Role — ver la Task Definition del frontend mas
# abajo, que omite `task_role_arn` por completo (argumento opcional en
# Fargate; sin el, el contenedor no tiene ningun credential expuesto vía el
# endpoint de metadata de la task).
resource "aws_iam_role" "backend_task" {
  name               = "${var.name_prefix}-ecs-backend-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(var.tags, { Name = "${var.name_prefix}-ecs-backend-task" })
}

# Acceso S3 de minimo privilegio, derivado directamente de las operaciones
# boto3 reales que ejecuta app/services/artifact_storage.py::S3ArtifactStorage
# (Fase 4A) — no de una lista generica. Solo se crea si ya existe un bucket
# real (var.s3_artifact_bucket no vacio). El bucket en si no es un recurso
# de este modulo todavia. Adjunto unicamente al Task Role del backend — el
# frontend nunca recibe este permiso (no tiene Task Role en absoluto).
#
# Mapeo operacion boto3 -> permiso IAM (ver docs/aws/ECS_ALB_FOUNDATION.md):
#   put_object                        -> s3:PutObject
#   head_object (x3: delete/exists/head_metadata) -> s3:GetObject (HeadObject
#     NO es una accion IAM independiente; AWS la autoriza con GetObject)
#   delete_object (x2: delete/promote_pending)     -> s3:DeleteObject
#   generate_presigned_url("get_object", ...)      -> s3:GetObject (la
#     identidad que FIRMA la URL necesita el permiso que la URL autoriza)
#   generate_presigned_post (upload directo)       -> s3:PutObject (idem)
#   copy_object (promote_pending, pending->final, mismo bucket) -> s3:GetObject
#     sobre el origen + s3:PutObject sobre el destino (CopyObject TAMPOCO es
#     una accion IAM independiente)
# list_objects_v2 / multipart upload: no se usan en ningun lado del backend
# (grep sobre backend/app confirma que artifact_storage.py es el unico sitio
# que llama al cliente S3) -> sin s3:ListBucket, sin permisos de multipart.
resource "aws_iam_role_policy" "backend_task_s3" {
  count = var.s3_artifact_bucket == "" ? 0 : 1

  name = "${var.name_prefix}-ecs-backend-task-s3"
  role = aws_iam_role.backend_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
      ]
      Resource = [
        "arn:aws:s3:::${var.s3_artifact_bucket}/${var.s3_evidence_prefix}/*",
        "arn:aws:s3:::${var.s3_artifact_bucket}/${var.s3_report_prefix}/*",
      ]
    }]
  })
}

# ============================================================================
# Logs (awslogs minimo — dashboards/alarms/metric filters son Fase 4C.4)
# ============================================================================

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.name_prefix}/backend"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-logs" })
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${var.name_prefix}/frontend"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, { Name = "${var.name_prefix}-frontend-logs" })
}

resource "aws_cloudwatch_log_group" "backend_migrate" {
  name              = "/ecs/${var.name_prefix}/backend-migrate"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-migrate-logs" })
}

resource "aws_cloudwatch_log_group" "backend_bootstrap" {
  name              = "/ecs/${var.name_prefix}/backend-bootstrap"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-bootstrap-logs" })
}

# ============================================================================
# Security group propio del frontend (item 22/23)
# ============================================================================
# El security group "ecs_tasks" de Fase 4C.1 se creo con alcance especifico
# a la API (ver su description: "Tasks ECS/Fargate de la API"), con ingress
# limitado a backend_container_port. El frontend es un servicio ECS
# independiente (item 20) con su propio puerto — reutilizarlo habria exigido
# ampliar el SG de la API para aceptar tambien el puerto del frontend,
# mezclando el blast radius de dos servicios con ciclos de vida distintos.
# En su lugar, este modulo crea un security group propio para el frontend
# y una regla de egress adicional en el SG del ALB (ya existente, id
# recibido via variable) hacia este nuevo SG — sin modificar ningun archivo
# del modulo security_groups de 4C.1. Ver docs/aws/ECS_ALB_FOUNDATION.md.

resource "aws_security_group" "frontend_tasks" {
  name        = "${var.name_prefix}-frontend-tasks"
  description = "Tasks ECS/Fargate del frontend: solo reciben trafico del ALB en el puerto del contenedor; salen hacia APIs de AWS (ECR, CloudWatch) via HTTPS."
  vpc_id      = var.vpc_id
  ingress     = []
  egress      = []

  tags = merge(var.tags, { Name = "${var.name_prefix}-frontend-tasks" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "frontend_from_alb" {
  security_group_id            = aws_security_group.frontend_tasks.id
  description                  = "Trafico del frontend unicamente desde el ALB."
  ip_protocol                  = "tcp"
  from_port                    = var.frontend_container_port
  to_port                      = var.frontend_container_port
  referenced_security_group_id = var.alb_security_group_id
}

resource "aws_vpc_security_group_egress_rule" "frontend_https_egress" {
  security_group_id = aws_security_group.frontend_tasks.id
  description       = "HTTPS saliente hacia APIs de AWS (ECR, CloudWatch) para pull de imagen y envio de logs."
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_frontend" {
  security_group_id            = var.alb_security_group_id
  description                  = "Reenvio del ALB hacia las tasks ECS del frontend."
  ip_protocol                  = "tcp"
  from_port                    = var.frontend_container_port
  to_port                      = var.frontend_container_port
  referenced_security_group_id = aws_security_group.frontend_tasks.id
}

# ============================================================================
# Container definitions
# ============================================================================

locals {
  # Variables de entorno no sensibles, comunes a los TRES containers de la
  # familia backend (service, migrate, bootstrap) — todo salvo POSTGRES_USER,
  # que difiere segun identidad (ver mas abajo, "Separacion de identidades",
  # docs/aws/RDS_PROXY_FOUNDATION.md). Los secretos (SECRET_KEY,
  # POSTGRES_PASSWORD, etc.) NUNCA aparecen aqui — viajan via `secrets`.
  backend_common_environment = concat(
    [
      { name = "PORT", value = tostring(var.backend_container_port) },
      { name = "APP_ENV", value = var.app_env },
      { name = "APP_DEBUG", value = "false" },
      { name = "ENABLE_API_DOCS", value = "false" },
      { name = "SECURE_HEADERS_ENABLED", value = "true" },
      { name = "POSTGRES_DB", value = var.db_name },
      { name = "POSTGRES_HOST", value = var.db_host },
      { name = "POSTGRES_PORT", value = tostring(var.db_port) },
      { name = "DB_POOL_SIZE", value = tostring(var.db_pool_size) },
      { name = "DB_MAX_OVERFLOW", value = tostring(var.db_max_overflow) },
      { name = "DB_POOL_TIMEOUT_SECONDS", value = tostring(var.db_pool_timeout_seconds) },
      { name = "DB_POOL_RECYCLE_SECONDS", value = tostring(var.db_pool_recycle_seconds) },
      { name = "DB_CONNECT_TIMEOUT_SECONDS", value = tostring(var.db_connect_timeout_seconds) },
      { name = "WEB_CONCURRENCY", value = tostring(var.web_concurrency) },
      { name = "BROWSER_COOKIE_SECURE", value = "true" },
      { name = "BROWSER_COOKIE_SAMESITE", value = "lax" },
      { name = "FRONTEND_ORIGINS", value = var.frontend_origins },
      { name = "BROWSER_ALLOWED_ORIGINS", value = var.browser_allowed_origins },
      { name = "TRUSTED_HOSTS", value = var.trusted_hosts },
      { name = "TERRITORY_AI_PROVIDER", value = "unavailable" },
      { name = "PUBLIC_FETCH_ALLOW_PRIVATE_HOSTS", value = "false" },
      { name = "METRICS_ENABLED", value = "false" },
      { name = "REPORT_OUTPUT_DIR", value = "/app/generated-reports" },
      { name = "EVIDENCE_OUTPUT_DIR", value = "/app/generated-evidence" },
      { name = "ARTIFACT_STORAGE_PROVIDER", value = var.artifact_storage_provider },
      { name = "AWS_REGION", value = var.aws_region },
    ],
    var.s3_artifact_bucket == "" ? [] : [
      { name = "S3_ARTIFACT_BUCKET", value = var.s3_artifact_bucket },
      # Mismos prefijos que autoriza aws_iam_role_policy.task_s3 mas abajo —
      # una sola fuente de verdad (var.s3_evidence_prefix/var.s3_report_prefix),
      # nunca duplicados a mano entre el entorno del contenedor y la policy IAM.
      { name = "S3_EVIDENCE_PREFIX", value = var.s3_evidence_prefix },
      { name = "S3_REPORT_PREFIX", value = var.s3_report_prefix },
    ],
  )

  extra_secrets = [
    for env_name, arn in var.secrets_manager_secret_arns : {
      name      = env_name
      valueFrom = arn
    }
  ]

  # --- Identidad de APLICACION: unicamente el ECS Service del backend en
  # runtime, siempre via RDS Proxy. Bajo privilegio (solo DML) — ver
  # modules/ecs, aws_ecs_task_definition.backend_bootstrap, que es quien
  # crea/actualiza este rol en PostgreSQL con las credenciales MAESTRAS.
  backend_service_environment = concat(local.backend_common_environment, [
    { name = "POSTGRES_USER", value = var.db_app_user },
  ])
  backend_service_secrets = concat(
    [{ name = "POSTGRES_PASSWORD", valueFrom = "${var.db_app_secret_arn}:password::" }],
    local.extra_secrets,
  )

  # --- Identidad MAESTRA: unicamente bootstrap y migration task — nunca el
  # ECS Service del backend (item 2 de la revision de 4C.3).
  backend_admin_environment = concat(local.backend_common_environment, [
    { name = "POSTGRES_USER", value = var.db_master_user },
  ])
  backend_admin_secrets = concat(
    [{ name = "POSTGRES_PASSWORD", valueFrom = "${var.db_master_secret_arn}:password::" }],
    local.extra_secrets,
  )

  backend_container_definition = {
    name      = "api"
    image     = var.backend_image
    essential = true
    # Fase 4B / DEPLOYMENT.md: Alembic NUNCA corre por replica en una
    # topologia multi-task — dos tasks migrando en paralelo compiten por
    # crear `alembic_version` (reproducido en Fase 4B). El CMD por defecto
    # del Dockerfile (`alembic upgrade head && exec uvicorn ...`) se
    # sobreescribe aqui para arrancar unicamente uvicorn: el mismo patron
    # que docker-compose.multi-instance.yml ya probo para `api-b`. La
    # migracion es la task definition separada aws_ecs_task_definition.backend_migrate
    # de abajo. Ver docs/aws/ECS_ALB_FOUNDATION.md, "Estrategia de migraciones".
    command = ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${var.backend_container_port} --workers ${var.web_concurrency}"]
    portMappings = [{
      containerPort = var.backend_container_port
      protocol      = "tcp"
    }]
    # Identidad de APLICACION — nunca la maestra. Ver docs/aws/RDS_PROXY_FOUNDATION.md.
    environment = local.backend_service_environment
    secrets     = local.backend_service_secrets
    healthCheck = {
      # Mismo comando que ya usa docker-compose.prod.yml — contra
      # /api/v1/health (liveness), no /api/v1/ready.
      command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:${var.backend_container_port}/api/v1/health')"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
  }

  # Release task de migracion: mismo entorno/imagen que el backend, pero
  # corre `alembic upgrade head` una sola vez y termina, con la identidad
  # MAESTRA (Alembic necesita poder crear/alterar tablas, indices y, en la
  # primera migracion del historial, la extension PostGIS — privilegios que
  # el usuario de aplicacion nunca tiene). Nunca se adjunta a un
  # aws_ecs_service — se invoca manualmente (aws ecs run-task) antes de
  # actualizar el servicio backend. Ver docs/aws/ECS_ALB_FOUNDATION.md y
  # docs/aws/RDS_PROXY_FOUNDATION.md, "Secuencia de bootstrap".
  backend_migrate_container_definition = {
    name        = "migrate"
    image       = var.backend_image
    essential   = true
    command     = ["/bin/sh", "-c", "exec alembic upgrade head"]
    environment = local.backend_admin_environment
    secrets     = local.backend_admin_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend_migrate.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "migrate"
      }
    }
  }

  # Bootstrap administrativo: crea o actualiza el rol de PostgreSQL de
  # APLICACION (var.db_app_user) con permisos DML minimos (SELECT/INSERT/
  # UPDATE/DELETE sobre el esquema public, sin CREATEROLE/CREATEDB/
  # rds_superuser) — nunca ejecutado por una replica del backend, nunca
  # parte de un aws_ecs_service. Usa la identidad MAESTRA (crear un rol
  # requiere privilegio administrativo). Reutiliza psycopg, ya presente en
  # la imagen del backend (requirements.txt) — cero cambios de codigo de
  # aplicacion. Idempotente: seguro de re-ejecutar en cualquier momento. Ver
  # docs/aws/RDS_PROXY_FOUNDATION.md, "Bootstrap administrativo".
  db_bootstrap_script = <<-PYEOF
    import os
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    )
    master_user = os.environ["POSTGRES_USER"]
    app_user = os.environ["APP_DB_USERNAME"]
    app_password = os.environ["APP_DB_PASSWORD"]
    db_name = os.environ["POSTGRES_DB"]

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (app_user,))
        if cur.fetchone() is None:
            cur.execute(
                sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(app_user)),
                (app_password,),
            )
        else:
            cur.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(app_user)),
                (app_password,),
            )
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(db_name), sql.Identifier(app_user)))
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(app_user)))
        cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
            sql.Identifier(app_user)))
        cur.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
            sql.Identifier(app_user)))
        cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(
            sql.Identifier(master_user), sql.Identifier(app_user)))
        cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(
            sql.Identifier(master_user), sql.Identifier(app_user)))

    conn.close()
    print("bootstrap: application role ready")
  PYEOF

  backend_bootstrap_container_definition = {
    name      = "bootstrap"
    image     = var.backend_image
    essential = true
    command   = ["/bin/sh", "-c", "exec python3 <<'PYEOF'\n${local.db_bootstrap_script}\nPYEOF"]
    environment = concat(local.backend_admin_environment, [
      { name = "APP_DB_USERNAME", value = var.db_app_user },
    ])
    secrets = concat(local.backend_admin_secrets, [
      { name = "APP_DB_PASSWORD", valueFrom = "${var.db_app_secret_arn}:password::" },
    ])
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend_bootstrap.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "bootstrap"
      }
    }
  }

  # El frontend (nginx) no consume ninguna variable de entorno en runtime —
  # su configuracion (nginx.conf) se hornea en la imagen en build time,
  # igual que hoy en docker-compose.prod.yml.
  frontend_container_definition = {
    name      = "frontend"
    image     = var.frontend_image
    essential = true
    portMappings = [{
      containerPort = var.frontend_container_port
      protocol      = "tcp"
    }]
    healthCheck = {
      # Mismo HEALTHCHECK que ya define frontend/Dockerfile.
      command     = ["CMD-SHELL", "wget -q -O - http://127.0.0.1:${var.frontend_container_port}/health || exit 1"]
      interval    = 30
      timeout     = 3
      retries     = 3
      startPeriod = 10
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "frontend"
      }
    }
  }
}

# ============================================================================
# Task Definitions
# ============================================================================

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.name_prefix}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_task_cpu
  memory                   = var.backend_task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.backend_task.arn

  container_definitions = jsonencode([local.backend_container_definition])

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend" })
}

resource "aws_ecs_task_definition" "backend_migrate" {
  family                   = "${var.name_prefix}-backend-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_task_cpu
  memory                   = var.backend_task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.backend_task.arn

  container_definitions = jsonencode([local.backend_migrate_container_definition])

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-migrate" })
}

resource "aws_ecs_task_definition" "backend_bootstrap" {
  family                   = "${var.name_prefix}-backend-bootstrap"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_task_cpu
  memory                   = var.backend_task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.backend_task.arn

  container_definitions = jsonencode([local.backend_bootstrap_container_definition])

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-bootstrap" })
}

# Sin task_role_arn: nginx estatico no ejecuta AWS SDK ni necesita ningun
# permiso runtime de AWS (Fase 4C.7 — antes heredaba el Task Role del
# backend, con permisos S3 que nunca invocaba). `task_role_arn` es un
# argumento opcional de aws_ecs_task_definition/Fargate; omitirlo deja al
# contenedor del frontend sin ninguna credencial de AWS disponible via el
# endpoint de metadata de la task.
resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.name_prefix}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend_task_cpu
  memory                   = var.frontend_task_memory
  execution_role_arn       = aws_iam_role.frontend_execution.arn

  container_definitions = jsonencode([local.frontend_container_definition])

  tags = merge(var.tags, { Name = "${var.name_prefix}-frontend" })
}

# ============================================================================
# ECS Services
# ============================================================================

resource "aws_ecs_service" "backend" {
  name            = "${var.name_prefix}-backend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 100 - var.fargate_spot_weight_percent
    base              = var.backend_desired_count
  }

  dynamic "capacity_provider_strategy" {
    for_each = var.fargate_spot_weight_percent > 0 ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = var.fargate_spot_weight_percent
    }
  }

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.ecs_tasks_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.backend_target_group_arn
    container_name   = "api"
    container_port   = var.backend_container_port
  }

  health_check_grace_period_seconds = var.backend_health_check_grace_period_seconds

  deployment_minimum_healthy_percent = var.deployment_minimum_healthy_percent
  deployment_maximum_percent         = var.deployment_maximum_percent

  # Rollback automatico ante un deployment fallido (item 16), sin
  # arquitectura blue/green adicional.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_iam_role_policy_attachment.execution_managed]

  tags = merge(var.tags, { Name = "${var.name_prefix}-backend" })

  # Bloquea en plan/apply dos combinaciones invalidas de storage de
  # artifacts que "terraform validate" no puede detectar (dependen de
  # valores concretos de variables, no solo de tipos):
  lifecycle {
    precondition {
      # ECS/Fargate: cada task tiene su propio filesystem efimero, no
      # compartido entre replicas — con mas de una replica, "local" perderia
      # o dejaria inconsistente la evidencia/actas/informes segun que task
      # atendio cada request (ver docs/aws/ECS_ALB_FOUNDATION.md).
      condition     = !(var.artifact_storage_provider == "local" && var.backend_desired_count > 1)
      error_message = "artifact_storage_provider=\"local\" no es valido con backend_desired_count > 1: cada task ECS tiene su propio filesystem, no compartido entre replicas. Usar artifact_storage_provider=\"s3\" (el valor por defecto) con s3_artifact_bucket configurado, o mantener backend_desired_count = 1."
    }

    precondition {
      # backend/app/core/config.py exige S3_ARTIFACT_BUCKET cuando
      # ARTIFACT_STORAGE_PROVIDER=s3 — sin esto la task fallaria al arrancar
      # (Settings() lanza ValueError). Falla aqui, en plan, en vez de en un
      # CrashLoop de ECS.
      condition     = !(var.artifact_storage_provider == "s3" && var.s3_artifact_bucket == "")
      error_message = "artifact_storage_provider=\"s3\" requiere s3_artifact_bucket: sin el, el backend fallaria al arrancar (backend/app/core/config.py exige S3_ARTIFACT_BUCKET cuando ARTIFACT_STORAGE_PROVIDER=s3). Proveer s3_artifact_bucket, o usar artifact_storage_provider=\"local\" solo con backend_desired_count = 1."
    }
  }
}

resource "aws_ecs_service" "frontend" {
  name            = "${var.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 100 - var.fargate_spot_weight_percent
    base              = var.frontend_desired_count
  }

  dynamic "capacity_provider_strategy" {
    for_each = var.fargate_spot_weight_percent > 0 ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = var.fargate_spot_weight_percent
    }
  }

  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [aws_security_group.frontend_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.frontend_target_group_arn
    container_name   = "frontend"
    container_port   = var.frontend_container_port
  }

  health_check_grace_period_seconds = var.frontend_health_check_grace_period_seconds

  deployment_minimum_healthy_percent = var.deployment_minimum_healthy_percent
  deployment_maximum_percent         = var.deployment_maximum_percent

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_iam_role_policy_attachment.frontend_execution_managed]

  tags = merge(var.tags, { Name = "${var.name_prefix}-frontend" })
}

# ============================================================================
# Autoscaling base (item 19) — target tracking por CPU, sin metricas custom
# de CloudWatch. Dimensionamiento definitivo: Fase 4C.6.
# ============================================================================

resource "aws_appautoscaling_target" "backend" {
  max_capacity       = var.backend_max_capacity
  min_capacity       = var.backend_min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${var.name_prefix}-backend-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = var.backend_cpu_target_value
  }
}

resource "aws_appautoscaling_target" "frontend" {
  max_capacity       = var.frontend_max_capacity
  min_capacity       = var.frontend_min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.frontend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "frontend_cpu" {
  name               = "${var.name_prefix}-frontend-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.frontend.resource_id
  scalable_dimension = aws_appautoscaling_target.frontend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.frontend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = var.frontend_cpu_target_value
  }
}
