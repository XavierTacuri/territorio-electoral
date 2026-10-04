output "instance_id" {
  description = "ID de la instancia EC2 de test-vps."
  value       = aws_instance.this.id
}

output "public_ip" {
  description = "IP publica ACTUAL de la instancia. Cambia tras un STOP/START (no hay Elastic IP) — volver a leer este output despues de un START."
  value       = aws_instance.this.public_ip
}

output "public_dns" {
  description = "DNS publico ACTUAL de la instancia (mismo ciclo de vida que public_ip)."
  value       = aws_instance.this.public_dns
}

output "test_url" {
  description = "URL de prueba (HTTP, sin dominio todavia)."
  value       = "http://${aws_instance.this.public_ip}"
}
