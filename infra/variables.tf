variable "alert_email" {
  description = "Where alerts go. Set it in infra/terraform.tfvars (git-ignored)."
  type        = string
}

variable "calls_per_day" {
  description = "Calls Mia takes per day across everyone (each call spends money)."
  type        = number
  default     = 60
}
