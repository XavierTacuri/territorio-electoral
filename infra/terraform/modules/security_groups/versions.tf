terraform {
  required_version = ">= 1.7.0, < 2.0.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # >= 5.27 concretamente: version minima en la que
      # aws_vpc_security_group_ingress_rule / egress_rule (usados aqui para
      # evitar ciclos de dependencia entre security groups) estan
      # disponibles de forma estable.
      version = ">= 5.27.0, < 6.0.0"
    }
  }
}
