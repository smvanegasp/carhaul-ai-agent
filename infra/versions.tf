terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  # Created by infra/bootstrap. Native S3 lockfile, no DynamoDB lock table.
  # The bucket name ends in the AWS account ID; bootstrap prints it (state_bucket).
  backend "s3" {
    bucket       = "carhaul-tfstate-816940506502"
    key          = "carhaul/terraform.tfstate"
    region       = "us-east-1"
    profile      = "carhaul"
    encrypt      = true
    use_lockfile = true
  }
}

# Same AWS account as fit and the pantry, fully separate stack: everything here is carhaul-*.
provider "aws" {
  region  = "us-east-1"
  profile = "carhaul"
  default_tags {
    tags = { app = "carhaul" }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name       = "carhaul"
  account_id = data.aws_caller_identity.current.account_id
  # Secrets live here as SecureStrings, put there by scripts/set_aws_secrets.py (never Terraform).
  ssm_prefix = "/carhaul/"
}
