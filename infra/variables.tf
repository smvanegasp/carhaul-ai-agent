variable "alert_email" {
  description = "Where alerts go. Set it in infra/terraform.tfvars (git-ignored)."
  type        = string
}

variable "calls_per_ip_per_hour" {
  description = "Calls one IP can start per hour (was 6; two testers hit it on 2026-11-11)."
  type        = number
  default     = 20
}

variable "calls_per_day" {
  description = "Calls Mia takes per day across everyone (each call spends money)."
  type        = number
  default     = 60
}
