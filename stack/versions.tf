terraform {
  required_version = ">= 1.5.0, < 2.0.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 8.0"
    }
  }
}

# Local: OCI SDK configuration/environment. Resource Manager: execution identity.
# Credentials are never stored in Terraform variables.
provider "oci" {
  region = var.region
}

