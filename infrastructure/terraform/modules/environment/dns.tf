resource "aws_route53_record" "app" {
  count   = var.route53_zone_id != "" && var.app_domain != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.app_domain
  type    = "A"
  ttl     = 300
  records = [aws_eip.app.public_ip]
}
