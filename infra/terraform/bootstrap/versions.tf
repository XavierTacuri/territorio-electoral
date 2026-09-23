terraform {
  # Mismo piso que environments/prod (que hoy no requiere un piso mayor por
  # si mismo — ese >= 1.11.0 efectivo lo impone unicamente modules/database,
  # que este bootstrap no usa). Sin necesidad de subirlo aqui.
  required_version = ">= 1.7.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.27.0, < 6.0.0"
    }
  }

  # Backend intencionalmente sin configurar (Fase 4D.1): este stack CREA el
  # bucket que environments/prod usara como backend remoto — no puede
  # depender de si mismo antes de existir (problema del huevo y la
  # gallina). El state de este bootstrap permanece LOCAL de forma
  # deliberada y permanente salvo migracion futura explicita — ver
  # docs/aws/AWS_BOOTSTRAP.md, seccion "State del propio bootstrap".
}
