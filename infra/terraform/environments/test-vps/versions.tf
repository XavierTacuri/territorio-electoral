terraform {
  # Mismo piso que environments/prod (ver ese versions.tf) — ningun recurso
  # de este stack exige una version mas nueva.
  required_version = ">= 1.7.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.27.0, < 6.0.0"
    }
  }

  # Backend "s3" con configuracion PARCIAL, igual que environments/prod —
  # bucket/key/region se pasan en `terraform init` via -backend-config, nunca
  # hardcodeados aqui. La key usada (ver README de este directorio) es
  # "territorio-electoral/test-vps/terraform.tfstate": un state DISTINTO del
  # de environments/prod dentro del MISMO bucket (infra/terraform/bootstrap),
  # para no tocar nunca el state de prod.
  #
  # `terraform init -backend=false` sigue funcionando sin credenciales AWS,
  # igual que en environments/prod — ver infra/terraform/README.md.
  backend "s3" {}
}
