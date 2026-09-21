# ============================================================================
# Ownership del bucket (ver docs/aws/BACKUP_DR_FOUNDATION.md, "Ownership del
# bucket de artifacts")
# ============================================================================
# El bucket de artifacts (var.bucket_name) NO es un recurso de este modulo ni
# de ningun otro modulo de este stack — lo confirma modules/ecs/main.tf
# (comentario sobre aws_iam_role_policy.task_s3: "El bucket en si no es un
# recurso de este modulo todavia") desde Fase 4C.2. Este modulo administra
# UNICAMENTE configuracion adjunta al bucket por NOMBRE (versioning,
# lifecycle, encryption por defecto, public access block) — recursos
# independientes del AWS provider que no requieren poseer/crear el propio
# `aws_s3_bucket`. Aun asi, activar cualquiera de ellos convierte a este
# stack en el OWNER real de esas configuraciones concretas: si otro
# stack/IaC ya administra el lifecycle o el versioning de ese mismo bucket,
# aplicar este modulo lo sobrescribiria (un `aws_s3_bucket_lifecycle_configuration`
# reemplaza TODA la lifecycle configuration del bucket, no la fusiona con
# reglas creadas por otro medio) — por eso activar este modulo exige TRES
# confirmaciones explicitas independientes, no una sola variable:
#
#   1. var.enabled                              — "quiero que este modulo haga algo"
#   2. var.bucket_configuration_managed_by_this_stack — "confirmo que NINGUN
#      otro stack/IaC administra hoy el versioning/lifecycle/encryption/
#      public-access-block de var.bucket_name"
#   3. var.bucket_dedicated_to_project           — "confirmo que var.bucket_name
#      esta dedicado exclusivamente a Territorio Electoral, no compartido
#      con otros proyectos/workloads"
#
# Las tres deben ser `true` simultaneamente (validado en `enabled` mas abajo)
# para que cualquier recurso se cree — cambiar una sola variable nunca activa
# nada por accidente. Ver tambien "Bucket dedicado" en
# docs/aws/BACKUP_DR_FOUNDATION.md sobre por que bucket_dedicated_to_project
# es ademas el prerequisito que justifica que abort-incomplete-multipart-upload
# y expired-delete-marker-cleanup (mas abajo) sean bucket-wide en vez de
# acotados por prefijo.
#
# Implicacion de "terraform destroy": destruiria estos recursos de
# configuracion (el bucket volveria a sus valores por defecto de AWS: sin
# versioning gestionado por Terraform, sin estas reglas de lifecycle, sin
# encryption/public-access-block gestionados por Terraform) — NUNCA el
# bucket en si ni sus objetos, porque `aws_s3_bucket` nunca se declara aqui.

variable "enabled" {
  description = "Interruptor maestro explicito. false (por defecto): este modulo no administra nada del bucket externo. true: los recursos de abajo se crean UNICAMENTE si ademas bucket_configuration_managed_by_this_stack=true y bucket_dedicated_to_project=true (validado abajo) y bucket_name no esta vacio — tres condiciones independientes, nunca una sola."
  type        = bool
  default     = false

  validation {
    condition     = !var.enabled || (var.bucket_configuration_managed_by_this_stack && var.bucket_dedicated_to_project)
    error_message = "enabled=true requiere ADEMAS bucket_configuration_managed_by_this_stack=true Y bucket_dedicated_to_project=true — dos confirmaciones explicitas independientes, no basta con esta variable. Este modulo administrara (y sobrescribira por completo, no fusionara) el versioning/lifecycle/encryption-por-defecto/public-access-block de bucket_name. Antes de poner las tres en true: (a) confirma que ningun otro stack/IaC administra hoy esas mismas configuraciones sobre ese bucket, y (b) confirma que ese bucket esta dedicado exclusivamente a Territorio Electoral, no compartido con otros proyectos. Ver docs/aws/BACKUP_DR_FOUNDATION.md, \"Ownership del bucket de artifacts\"."
  }
}

variable "bucket_configuration_managed_by_this_stack" {
  description = "false (por defecto). Confirmacion EXPLICITA de que ningun otro stack/IaC administra hoy el versioning, la lifecycle configuration, la encryption por defecto ni el public access block de var.bucket_name — aws_s3_bucket_lifecycle_configuration (y los otros tres recursos de este modulo) REEMPLAZAN por completo la configuracion existente del bucket para ese aspecto, no la fusionan. Poner esto en true sin haber verificado lo anterior podria borrar silenciosamente reglas manuales o de otro IaC que Terraform no conoce."
  type        = bool
  default     = false
}

variable "bucket_dedicated_to_project" {
  description = "false (por defecto). Confirmacion EXPLICITA de que var.bucket_name esta dedicado exclusivamente a Territorio Electoral (no es un bucket compartido con otros proyectos/workloads). Este modulo no puede comprobarlo tecnicamente (el bucket es externo, ver arriba) — es una decision operativa que el equipo confirma aqui. Ademas de gatear enabled (junto con bucket_configuration_managed_by_this_stack), es el prerequisito que justifica que las reglas bucket-wide de este modulo (abort-incomplete-multipart-upload, expired-delete-marker-cleanup) no esten acotadas por prefijo: si el bucket no fuera dedicado, esas reglas podrian afectar objetos de otros workloads ajenos a Territorio Electoral."
  type        = bool
  default     = false
}

variable "bucket_name" {
  description = "Nombre del bucket S3 externo (mismo valor que var.s3_artifact_bucket en environments/prod). Vacio (por defecto): ningun recurso se crea, independientemente de los demas valores."
  type        = string
  default     = ""
}

variable "evidence_prefix" {
  description = "Debe coincidir con S3_EVIDENCE_PREFIX (backend/app/core/config.py, default \"evidence\") — mismo valor que var.s3_evidence_prefix en environments/prod."
  type        = string
  default     = "evidence"
}

variable "report_prefix" {
  description = "Debe coincidir con S3_REPORT_PREFIX (backend/app/core/config.py, default \"reports\") — mismo valor que var.s3_report_prefix en environments/prod."
  type        = string
  default     = "reports"
}

# Sin variable "tags": ninguno de los recursos de este modulo
# (aws_s3_bucket_versioning, aws_s3_bucket_lifecycle_configuration,
# aws_s3_bucket_server_side_encryption_configuration,
# aws_s3_bucket_public_access_block) acepta un argumento tags — verificado
# contra el schema real del provider AWS 5.100.0. El propio bucket (no
# administrado aqui, ver arriba) es lo unico etiquetable.

# ============================================================================
# Versioning
# ============================================================================

variable "enable_versioning" {
  description = "true (por defecto): S3 Versioning activado — protege contra overwrite/delete accidental de evidencia/informes (docs/aws/PRODUCTION_ARCHITECTURE.md ya documentaba este valor como el target). Las reglas de noncurrent version de abajo solo tienen efecto si esto es true. IMPORTANTE (ver docs/aws/BACKUP_DR_FOUNDATION.md, \"Semantica de expiration con versioning\"): con versioning activo, una `expiration.days` sobre un objeto CURRENT nunca borra bytes de inmediato — inserta un delete marker como nueva version actual y la version anterior pasa a ser NONCURRENT, gobernada desde ese momento por las reglas noncurrent_version_* correspondientes a su prefijo, no por la regla de expiration."
  type        = bool
  default     = true
}

# ============================================================================
# Pending (evidence/pending/) — unico prefijo con expiracion CURRENT
# incondicional: objetos huerfanos de un upload-intent nunca completado
# (election_act_service.py::create_upload_intent), nunca referenciados por
# ninguna fila de base de datos. Con versioning activo, esta regla tambien
# gestiona sus propias versiones noncurrent con una retencion CORTA e
# independiente de la usada para evidencia final/reportes — un pending nunca
# tuvo valor de recuperacion mas alla de la ventana operativa normal de un
# upload, a diferencia de evidencia definitiva u informes.
# ============================================================================

variable "pending_expiration_days" {
  description = "Dias tras los que un objeto CURRENT bajo {evidence_prefix}/pending/ recibe accion de expiration. Con versioning=false: borrado fisico real a los N dias. Con versioning=true (default): a los N dias se inserta un delete marker (el objeto deja de ser 'visible'/current) y la version anterior pasa a noncurrent — el borrado fisico real ocurre despues, segun pending_noncurrent_expiration_days. Valor inicial conservador (PRODUCTION_ARCHITECTURE.md sugeria 24-48h)."
  type        = number
  default     = 2

  validation {
    condition     = var.pending_expiration_days >= 1
    error_message = "pending_expiration_days debe ser al menos 1."
  }
}

variable "pending_noncurrent_expiration_days" {
  description = "Solo con enable_versioning=true. Dias tras convertirse en noncurrent antes de borrar fisicamente una version antigua bajo {evidence_prefix}/pending/. Default CORTO (7 dias) y deliberadamente independiente de evidence_final_noncurrent_expiration_days/reports_noncurrent_expiration_days (90 dias cada uno, ver abajo): un pending nunca completado no tiene el mismo valor de recuperacion que evidencia definitiva o informes — no tiene sentido conservar sus versiones noncurrent con la misma retencion larga orientada a recuperacion ante overwrite accidental. Sin transicion a STANDARD_IA para pending (no se ofrece una variable propia): 7 dias es menor que el minimo de permanencia de 30 dias que exige esa clase, por lo que transicionar antes de expirar no tendria sentido economico."
  type        = number
  default     = 7

  validation {
    condition     = var.pending_noncurrent_expiration_days >= 1
    error_message = "pending_noncurrent_expiration_days debe ser al menos 1."
  }

  validation {
    condition     = var.pending_noncurrent_expiration_days <= var.evidence_final_noncurrent_expiration_days
    error_message = "pending_noncurrent_expiration_days debe ser menor o igual que evidence_final_noncurrent_expiration_days — un pending nunca completado no debe retener versiones noncurrent por mas tiempo que la evidencia definitiva."
  }
}

# ============================================================================
# Reports (reports/*) — expiracion CURRENT deshabilitada por defecto. Ver
# docs/aws/BACKUP_DR_FOUNDATION.md, "Auditoria de retencion real de reports"
# — la aplicacion es el mecanismo PRIMARIO de expiracion logica/fisica de
# reports/, para AMBOS backends: ReportService.deactivate() (manual, admin) y
# app/scripts/cleanup_generated_reports.py (automatico, por
# ReportArtifact.expires_on) construyen su storage via
# artifact_storage_factory.build_report_storage() — la unica fuente de
# verdad, la misma que usa ReportService — y por tanto llaman
# storage.delete() sobre el backend REAL configurado (local o S3). Corregido
# en la revision que auditó este defecto (antes, el script de limpieza
# automatica construia LocalReportStorage de forma hardcodeada y nunca
# tocaba S3 realmente); probado en tests/test_cleanup_generated_reports.py.
# Este 0 por defecto ya NO es una retencion fisica indefinida por un
# mecanismo roto — S3 lifecycle se concentra en recuperacion/versioning,
# noncurrent version cleanup y transiciones opcionales, no en duplicar la
# expiracion current que la aplicacion ya realiza correctamente.
# ============================================================================

variable "reports_expiration_days" {
  description = "0 (por defecto): sin expiracion CURRENT automatica de objetos bajo {report_prefix}/ — la aplicacion (ReportService.deactivate() y cleanup_generated_reports.py, ambos via artifact_storage_factory.build_report_storage()) ya es el mecanismo primario de expiracion, para local y S3 por igual. Un valor > 0 aqui anadiria una SEGUNDA expiracion current redundante; si se activa igualmente, debe ser mayor que report_artifact_retention_days (backend/app/core/config.py, default 30) para no competir con la ventana en la que la aplicacion todavia considera valido un artefacto."
  type        = number
  default     = 0

  validation {
    condition     = var.reports_expiration_days >= 0
    error_message = "reports_expiration_days debe ser 0 (deshabilitado) o mayor."
  }
}

# ============================================================================
# Evidencia final (evidence/final/) — SIN expiracion CURRENT, nunca. Solo
# transicion de storage class opcional, y su propia retencion noncurrent
# (mas larga, orientada a recuperacion) independiente de pending/reports.
# ============================================================================

variable "evidence_final_transition_enabled" {
  description = "false (por defecto): sin transicion automatica de storage class para {evidence_prefix}/final/. true: transiciona a evidence_final_transition_storage_class tras evidence_final_transition_days — evaluar cuidadosamente el costo de retrieval si la evidencia necesita consultarse con frecuencia (auditorias, reclamos)."
  type        = bool
  default     = false
}

variable "evidence_final_transition_days" {
  type    = number
  default = 90

  validation {
    condition     = var.evidence_final_transition_days >= 30
    error_message = "evidence_final_transition_days debe ser al menos 30 (STANDARD_IA exige un minimo de 30 dias de permanencia; transicionar antes genera cargos de storage minimo sin ahorro real)."
  }
}

variable "evidence_final_transition_storage_class" {
  description = "STANDARD_IA (por defecto): reduce costo de almacenamiento manteniendo recuperacion en milisegundos (a diferencia de GLACIER/DEEP_ARCHIVE, que exigen un restore previo). No se ofrece una cadena de transiciones mas compleja en esta fase — ver docs/aws/BACKUP_DR_FOUNDATION.md, \"Transiciones de storage class\"."
  type        = string
  default     = "STANDARD_IA"
}

variable "evidence_final_noncurrent_transition_enabled" {
  description = "Solo con enable_versioning=true. true (por defecto): las versiones noncurrent de {evidence_prefix}/final/ transicionan a STANDARD_IA tras evidence_final_noncurrent_transition_days — una version noncurrent ya no es la 'actual', tiene sentido economico moverla antes que a la version current equivalente."
  type        = bool
  default     = true
}

variable "evidence_final_noncurrent_transition_days" {
  type    = number
  default = 30

  validation {
    condition     = var.evidence_final_noncurrent_transition_days >= 30
    error_message = "evidence_final_noncurrent_transition_days debe ser al menos 30 (minimo de permanencia de STANDARD_IA)."
  }
}

variable "evidence_final_noncurrent_transition_storage_class" {
  type    = string
  default = "STANDARD_IA"
}

variable "evidence_final_noncurrent_expiration_days" {
  description = "Solo con enable_versioning=true. Dias tras convertirse en noncurrent antes de borrar fisicamente una version antigua bajo {evidence_prefix}/final/. 90 dias por defecto: ventana de recuperacion conservadora para evidencia definitiva ante un overwrite/delete accidental — deliberadamente mas larga que pending_noncurrent_expiration_days (7 dias), porque evidence/final/ tiene valor operativo/auditable que un pending nunca completado no tiene."
  type        = number
  default     = 90

  validation {
    condition     = var.evidence_final_noncurrent_expiration_days >= 1
    error_message = "evidence_final_noncurrent_expiration_days debe ser al menos 1."
  }
}

# ============================================================================
# Informes (reports/*) — transicion CURRENT opcional (independiente de la
# expiracion de arriba), y su propia retencion noncurrent independiente de
# evidence/pending y evidence/final.
# ============================================================================

variable "reports_transition_enabled" {
  type    = bool
  default = false
}

variable "reports_transition_days" {
  type    = number
  default = 90

  validation {
    condition     = var.reports_transition_days >= 30
    error_message = "reports_transition_days debe ser al menos 30 (minimo de permanencia de STANDARD_IA)."
  }
}

variable "reports_transition_storage_class" {
  type    = string
  default = "STANDARD_IA"
}

variable "reports_noncurrent_transition_enabled" {
  description = "Solo con enable_versioning=true. true (por defecto): las versiones noncurrent de {report_prefix}/ transicionan a STANDARD_IA tras reports_noncurrent_transition_days."
  type        = bool
  default     = true
}

variable "reports_noncurrent_transition_days" {
  type    = number
  default = 30

  validation {
    condition     = var.reports_noncurrent_transition_days >= 30
    error_message = "reports_noncurrent_transition_days debe ser al menos 30 (minimo de permanencia de STANDARD_IA)."
  }
}

variable "reports_noncurrent_transition_storage_class" {
  type    = string
  default = "STANDARD_IA"
}

variable "reports_noncurrent_expiration_days" {
  description = "Solo con enable_versioning=true. Dias tras convertirse en noncurrent antes de borrar fisicamente una version antigua bajo {report_prefix}/. 90 dias por defecto, configurado de forma independiente de evidence_final_noncurrent_expiration_days (mismo valor por defecto, pero variables separadas a proposito — los ciclos de vida de informes y evidencia son conceptualmente distintos aunque hoy compartan el mismo numero)."
  type        = number
  default     = 90

  validation {
    condition     = var.reports_noncurrent_expiration_days >= 1
    error_message = "reports_noncurrent_expiration_days debe ser al menos 1."
  }
}

# ============================================================================
# Delete markers huerfanos y multipart incompleto — bucket-wide (prefix ""),
# NO acotados por prefijo. Justificado UNICAMENTE porque bucket_dedicated_to_project
# (arriba) es un prerequisito obligatorio para que este modulo administre
# nada en absoluto — si el bucket no estuviera confirmado como dedicado a
# Territorio Electoral, estas dos reglas SI necesitarian acotarse por
# prefijo para no afectar objetos de otros workloads ajenos. Ver
# docs/aws/BACKUP_DR_FOUNDATION.md, "Alcance de multipart cleanup y delete
# marker cleanup".
# ============================================================================

variable "expired_object_delete_marker_cleanup_enabled" {
  type    = bool
  default = true
}

variable "abort_incomplete_multipart_upload_days" {
  type    = number
  default = 7

  validation {
    condition     = var.abort_incomplete_multipart_upload_days >= 1
    error_message = "abort_incomplete_multipart_upload_days debe ser al menos 1."
  }
}

# ============================================================================
# Encryption por defecto del bucket (defensa en profundidad: la aplicacion
# ya envia ServerSideEncryption en cada put_object/presigned POST — ver
# S3ArtifactStorage._encryption_args — esto cubre ademas cualquier objeto
# escrito sin ese header, ej. una subida manual via consola/CLI). Sujeto al
# mismo gate de ownership que el resto del modulo (enabled +
# bucket_configuration_managed_by_this_stack + bucket_dedicated_to_project)
# — este stack no debe competir con otro IaC por la encryption configuration
# por defecto del bucket, igual que con el lifecycle/versioning.
# ============================================================================

variable "enable_default_encryption" {
  type    = bool
  default = true
}

variable "sse_mode" {
  description = "AES256 (por defecto) o aws:kms — mismos dos valores validos que S3_SSE_MODE en backend/app/core/config.py. Migrar a aws:kms con una CMK dedicada es una decision futura, no forzada aqui."
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "aws:kms"], var.sse_mode)
    error_message = "sse_mode debe ser \"AES256\" o \"aws:kms\"."
  }
}

variable "kms_key_id" {
  description = "ARN/ID de la CMK, obligatorio si sse_mode = \"aws:kms\". Sin valor por defecto: no se crea ninguna CMK automaticamente."
  type        = string
  default     = ""

  validation {
    condition     = var.sse_mode != "aws:kms" || (var.kms_key_id != null && trimspace(var.kms_key_id) != "")
    error_message = "kms_key_id es obligatorio cuando sse_mode = \"aws:kms\"."
  }
}

# ============================================================================
# Public Access Block — mismo gate de ownership que el resto del modulo.
# ============================================================================

variable "enable_public_access_block" {
  description = "true (por defecto): las 4 protecciones de Block Public Access activas. El bucket de artifacts nunca debe ser publico — los uploads/downloads directos usan URLs firmadas (S3ArtifactStorage.download/presign_upload), nunca ACLs ni policies publicas."
  type        = bool
  default     = true
}
