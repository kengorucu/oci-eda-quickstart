variable "region" {
  default     = "eu-frankfurt-1"
  description = "OCI region with E6 managed-node support."
  type        = string
}

variable "compartment_ocid" {
  description = "Existing compartment for the cluster and networking."
  type        = string
}

variable "availability_domain" {
  description = "Exact tenancy-specific AD name with E6 capacity."
  type        = string
}

variable "kubernetes_version" {
  description = "Explicit currently supported OKE Kubernetes version, including v prefix."
  type        = string
  validation {
    condition     = can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+$", var.kubernetes_version))
    error_message = "Use a full OKE version such as v1.xx.y, selected from current node-pool options."
  }
}

variable "node_image_ocid" {
  description = "Optional explicit OKE image override. Leave empty to discover a matching image automatically."
  type        = string
  default     = ""
  nullable    = false
}

variable "node_os_major_version" {
  description = "Oracle Linux major version for automatic OKE x86_64 image selection."
  type        = string
  default     = "9"
  validation {
    condition     = contains(["8", "9"], var.node_os_major_version)
    error_message = "Choose Oracle Linux 8 or 9."
  }
}

variable "admin_cidr" {
  description = "Trusted IPv4 egress CIDR allowed to access the public Kubernetes API, usually your-public-ip/32."
  type        = string
  validation {
    condition     = can(cidrnetmask(var.admin_cidr)) && try(tonumber(split("/", var.admin_cidr)[1]) >= 24, false)
    error_message = "Use a trusted IPv4 /24 or narrower; /32 is recommended."
  }
}

variable "name" {
  description = "Resource name prefix."
  type        = string
  default     = "eda-e6-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.name))
    error_message = "Use 3-25 lowercase letters, digits, or hyphens, beginning with a letter."
  }
}

variable "node_count" {
  type        = number
  description = "Two E6 workers for one-worker and two-worker benchmark runs."
  default     = 2
  validation {
    condition     = var.node_count == 2 && floor(var.node_count) == var.node_count
    error_message = "This matched comparison requires exactly two E6 nodes."
  }
}

variable "node_ocpus" {
  type        = number
  description = "Physical cores per x86 worker. One OCPU normally exposes two Kubernetes logical CPUs with SMT enabled."
  default     = 16
  validation {
    condition     = var.node_ocpus >= 2 && var.node_ocpus <= 94 && floor(var.node_ocpus) == var.node_ocpus
    error_message = "Select an integer between 2 and 94 OCPUs, subject to both E6 shape limits."
  }
}

variable "node_memory_gbs" {
  type        = number
  description = "RAM per node in GB; must also satisfy the selected shape's memory/core limits."
  default     = 128
  validation {
    condition     = var.node_memory_gbs >= 16 && var.node_memory_gbs <= 712 && floor(var.node_memory_gbs) == var.node_memory_gbs
    error_message = "Select an integer between 16 and 712 GB."
  }
}


