# The app's own address, optional. Empty (the default) serves the site on its cloudfront.net
# address only. To add one, set `domain = "carhaul.sergiovanegas.com"` in terraform.tfvars and
# apply; DNS lives at Hostinger (sergiovanegas.com), so two records are added there by hand:
#   1. ACM's validation CNAME (output certificate_validation_record) proves the domain is ours.
#   2. carhaul -> the CloudFront domain (output dns_target) sends visitors to the app.
# The cloudfront.net address keeps working too.

variable "domain" {
  description = "The app's own address (e.g. carhaul.sergiovanegas.com). Empty: only the cloudfront.net address."
  type        = string
  default     = ""
}

locals {
  custom_domain = var.domain != ""
}

# CloudFront only uses certificates from us-east-1, which is this stack's region.
resource "aws_acm_certificate" "app" {
  count             = local.custom_domain ? 1 : 0
  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Waits until ACM sees the validation record at Hostinger (usually minutes after adding it).
resource "aws_acm_certificate_validation" "app" {
  count           = local.custom_domain ? 1 : 0
  certificate_arn = aws_acm_certificate.app[0].arn

  timeouts {
    create = "2h"
  }
}

output "certificate_validation_record" {
  description = "Add this CNAME at Hostinger (Name without the trailing .sergiovanegas.com.)."
  value = [for o in flatten(aws_acm_certificate.app[*].domain_validation_options) : {
    name  = o.resource_record_name
    type  = o.resource_record_type
    value = o.resource_record_value
  }]
}

output "dns_target" {
  description = "At Hostinger: CNAME for the domain -> this."
  value       = aws_cloudfront_distribution.main.domain_name
}
