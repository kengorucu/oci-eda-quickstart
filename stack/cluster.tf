data "oci_containerengine_node_pool_option" "regional" {
  node_pool_option_id   = "all"
  compartment_id        = var.compartment_ocid
  node_pool_k8s_version = var.kubernetes_version
  node_pool_os_arch     = "X86_64"
}

resource "oci_containerengine_cluster" "poc" {
  compartment_id     = var.compartment_ocid
  vcn_id             = oci_core_vcn.poc.id
  name               = var.name
  kubernetes_version = var.kubernetes_version
  type               = "BASIC_CLUSTER"
  freeform_tags      = local.tags
  endpoint_config {
    subnet_id            = oci_core_subnet.api.id
    is_public_ip_enabled = true
  }
  cluster_pod_network_options {
    cni_type = "FLANNEL_OVERLAY"
  }
  options {
    kubernetes_network_config {
      pods_cidr     = "10.244.0.0/16"
      services_cidr = "10.96.0.0/16"
    }
    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
  }
  lifecycle {
    precondition {
      condition     = contains(data.oci_containerengine_node_pool_option.regional.kubernetes_versions, var.kubernetes_version)
      error_message = "The selected Kubernetes version is not advertised by OKE in this region."
    }
  }
}

data "oci_core_image_shape" "compatible" {
  image_id   = local.selected_node_image_id
  shape_name = "VM.Standard.E6.Flex"
}

resource "oci_containerengine_node_pool" "e6" {
  compartment_id     = var.compartment_ocid
  cluster_id         = oci_containerengine_cluster.poc.id
  name               = "${var.name}-workers"
  kubernetes_version = var.kubernetes_version
  node_shape         = data.oci_core_image_shape.compatible.shape
  freeform_tags      = local.tags
  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gbs
  }
  node_config_details {
    size = var.node_count
    placement_configs {
      availability_domain = var.availability_domain
      subnet_id           = oci_core_subnet.workers.id
    }
    node_pool_pod_network_option_details {
      cni_type = "FLANNEL_OVERLAY"
    }
    freeform_tags = local.tags
  }
  node_source_details {
    source_type             = "IMAGE"
    image_id                = local.selected_node_image_id
    boot_volume_size_in_gbs = 100
  }
  initial_node_labels {
    key   = "workload"
    value = "eda-regression"
  }
  initial_node_labels {
    key   = "compute-family"
    value = "e6"
  }
  lifecycle {
    precondition {
      condition     = contains(data.oci_containerengine_node_pool_option.regional.shapes, "VM.Standard.E6.Flex")
      error_message = "OKE does not advertise this shape in the selected region. Check E6 support and AD capacity."
    }
    precondition {
      condition     = local.selected_node_image_id != ""
      error_message = "No matching Oracle Linux OKE x86_64 image was found for this Kubernetes version and OS major version. Check the version or choose another Oracle Linux major version; no resources should be applied until Plan succeeds."
    }
    precondition {
      condition     = contains([for s in data.oci_containerengine_node_pool_option.regional.sources : s.image_id], local.selected_node_image_id)
      error_message = "The selected image must be advertised by OKE for the chosen Kubernetes version and x86_64 architecture."
    }
    precondition {
      condition     = var.node_memory_gbs >= var.node_ocpus && var.node_memory_gbs <= 64 * var.node_ocpus
      error_message = "Memory must be between 1 and 64 GB per OCPU, subject to the selected shape limits."
    }
  }
}

