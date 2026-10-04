# Los tres artefactos de abajo (compose, start.sh, unit systemd) no llevan
# ningun secreto -- se renderizan en claro y se incrustan en user_data en
# base64 solo para evitar problemas de escapado de heredoc, no por
# confidencialidad. Los secretos reales (POSTGRES_PASSWORD, SECRET_KEY, ...)
# los genera start.sh el PRIMER arranque real, directamente en el disco de
# la instancia -- nunca pasan por Terraform ni por este archivo.

locals {
  docker_compose_rendered = templatefile("${path.module}/templates/docker-compose.yml.tpl", {
    backend_image  = local.backend_image
    frontend_image = local.frontend_image
  })

  start_script_rendered = templatefile("${path.module}/templates/start.sh.tpl", {
    aws_region        = var.aws_region
    ecr_registry_host = local.ecr_registry_host
  })

  systemd_unit_rendered = file("${path.module}/templates/territorio-electoral.service.tpl")

  user_data_rendered = templatefile("${path.module}/templates/user_data.sh.tpl", {
    compose_version    = var.compose_version
    docker_compose_b64 = base64encode(local.docker_compose_rendered)
    start_script_b64   = base64encode(local.start_script_rendered)
    systemd_unit_b64   = base64encode(local.systemd_unit_rendered)
  })
}

resource "aws_instance" "this" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  # Sin Elastic IP (regla dura de la fase): la IP publica cambia tras un
  # STOP/START, y start.sh la recalcula via IMDSv2 en cada arranque.
  associate_public_ip_address = true

  metadata_options {
    http_tokens   = "required" # IMDSv2 obligatorio
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data                   = local.user_data_rendered
  user_data_replace_on_change = true

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-instance" })
}
