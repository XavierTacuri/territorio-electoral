# Variables del bucket S3 de artifacts (evidencia/informes) DE ESTE STACK —
# a diferencia de modules/s3_lifecycle (que historicamente asumia un bucket
# externo, ver docs/aws/BACKUP_DR_FOUNDATION.md, "Ownership del bucket de
# artifacts"), este modulo SI declara `aws_s3_bucket`: es el owner real del
# recurso, de su versioning, su encryption por defecto y su public access
# block. modules/s3_lifecycle sigue administrando UNICAMENTE la lifecycle
# configuration sobre el nombre que este modulo produce — ningun aspecto se
# administra dos veces desde dos modulos distintos.

variable "bucket_name" {
  description = "Nombre GLOBALMENTE UNICO del bucket S3 (mismo valor que var.s3_artifact_bucket_name en environments/prod). Sin default: nunca se inventa un nombre de bucket real — mismo criterio que state_bucket_name en infra/terraform/bootstrap. RECOMENDADO para este proyecto: evitar \".\" en el nombre (aunque la regla oficial de S3 lo permite, ver validations abajo) — un nombre con puntos rompe la validacion de certificado TLS wildcard de S3 en acceso virtual-hosted-style (*.s3.amazonaws.com), degradando a HTTP o a path-style; un nombre solo con letras/digitos/guiones evita ese problema por completo."
  type        = string

  # Mismas 7 reglas oficiales de nombres de bucket S3 (General Purpose
  # Buckets) que environments/prod/variables.tf exige sobre
  # s3_artifact_bucket_name — repetidas aqui, no relajadas ni delegadas,
  # para que este modulo sea seguro y valido incluso si se reutiliza fuera de
  # environments/prod (un caller que pase un bucket_name invalido nunca lo
  # descubriria si esta validacion dependiera exclusivamente del caller). Cada
  # regla en su propia validation — mas legible y mantenible que una unica
  # regex monolitica, y cada mensaje de error senala exactamente que regla se
  # violo.

  validation {
    condition     = length(var.bucket_name) >= 3 && length(var.bucket_name) <= 63
    error_message = "bucket_name debe tener entre 3 y 63 caracteres."
  }

  validation {
    condition     = can(regex("^[a-z0-9.-]+$", var.bucket_name))
    error_message = "bucket_name solo puede contener minusculas (a-z), digitos (0-9), puntos (.) y guiones (-) — sin mayusculas, guiones bajos ni ningun otro caracter."
  }

  validation {
    condition     = can(regex("^[a-z0-9].*[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name debe empezar y terminar con una letra minuscula o un digito — nunca con un punto o un guion."
  }

  validation {
    condition     = !can(regex("\\.\\.", var.bucket_name))
    error_message = "bucket_name no puede contener dos puntos consecutivos (\"..\")."
  }

  validation {
    condition     = !can(regex("^[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$", var.bucket_name))
    error_message = "bucket_name no puede tener formato de direccion IPv4 (ej. \"192.168.1.1\") — prohibido por las reglas de S3, independientemente de si los octetos son validos como IP real."
  }

  validation {
    condition     = !can(regex("^(xn--|sthree-|amzn-s3-demo-)", var.bucket_name))
    error_message = "bucket_name no puede empezar con un prefijo reservado por AWS: \"xn--\", \"sthree-\" o \"amzn-s3-demo-\"."
  }

  validation {
    condition     = !can(regex("(-s3alias|--ol-s3|\\.mrap|--x-s3|--table-s3)$", var.bucket_name))
    error_message = "bucket_name no puede terminar con un sufijo reservado por AWS: \"-s3alias\", \"--ol-s3\", \".mrap\", \"--x-s3\" o \"--table-s3\"."
  }
}

variable "enable_versioning" {
  description = "true (por defecto): S3 Versioning activado — protege contra overwrite/delete accidental de evidencia/informes. modules/s3_lifecycle recibe el mismo valor (var.s3_versioning_enabled en environments/prod) para decidir si sus reglas de lifecycle incluyen noncurrent_version_* — una unica fuente de verdad, nunca dos booleans independientes que puedan desincronizarse."
  type        = bool
  default     = true
}

variable "sse_mode" {
  description = "AES256 (por defecto) o aws:kms — mismos dos valores validos que S3_SSE_MODE en backend/app/core/config.py."
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "aws:kms"], var.sse_mode)
    error_message = "sse_mode debe ser \"AES256\" o \"aws:kms\"."
  }
}

variable "kms_key_id" {
  description = "ARN/ID de la CMK, obligatorio si sse_mode = \"aws:kms\". Sin valor por defecto: no se crea ninguna CMK automaticamente (mismo criterio que el state bucket de infra/terraform/bootstrap)."
  type        = string
  default     = ""

  validation {
    condition     = var.sse_mode != "aws:kms" || (var.kms_key_id != null && trimspace(var.kms_key_id) != "")
    error_message = "kms_key_id es obligatorio cuando sse_mode = \"aws:kms\"."
  }
}

variable "tags" {
  description = "Tags a fusionar con el tag Name propio del bucket (misma convencion que el resto de modulos: common_tags via default_tags del provider, mas Name aqui)."
  type        = map(string)
  default     = {}
}
