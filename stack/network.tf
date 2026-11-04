locals {
  vcn_cidr    = "10.70.0.0/16"
  api_cidr    = "10.70.0.0/28"
  worker_cidr = "10.70.1.0/24"
  tags        = { project = var.name, purpose = "eda-performance-poc" }
}

resource "oci_core_vcn" "poc" {
  compartment_id = var.compartment_ocid
  cidr_block     = local.vcn_cidr
  display_name   = var.name
  dns_label      = "edapoc"
  freeform_tags  = local.tags
}

resource "oci_core_internet_gateway" "api" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.poc.id
  display_name   = "${var.name}-igw"
}

resource "oci_core_nat_gateway" "workers" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.poc.id
  display_name   = "${var.name}-nat"
}

data "oci_core_services" "regional" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

resource "oci_core_service_gateway" "workers" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.poc.id
  display_name   = "${var.name}-services"
  services {
    service_id = data.oci_core_services.regional.services[0].id
  }
}

resource "oci_core_route_table" "api" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.poc.id
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.api.id
  }
}

resource "oci_core_route_table" "workers" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.poc.id
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_nat_gateway.workers.id
  }
  route_rules {
    destination       = data.oci_core_services.regional.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.workers.id
  }
}

resource "oci_core_security_list" "api" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.poc.id
  display_name   = "${var.name}-api"
  ingress_security_rules {
    protocol    = "6"
    source      = var.admin_cidr
    description = "Operator Kubernetes API access"
    tcp_options {
      min = 6443
      max = 6443
    }
  }
  dynamic "ingress_security_rules" {
    for_each = toset([6443, 12250])
    content {
      protocol = "6"
      source   = local.worker_cidr
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
  ingress_security_rules {
    protocol = "1"
    source   = local.vcn_cidr
    icmp_options {
      type = 3
      code = 4
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_security_list" "workers" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.poc.id
  display_name   = "${var.name}-workers"
  ingress_security_rules {
    protocol    = "all"
    source      = local.worker_cidr
    description = "Internal worker and Flannel overlay communication"
  }
  ingress_security_rules {
    protocol    = "6"
    source      = local.api_cidr
    description = "Flannel: control-plane TCP access to worker and pod endpoints"
  }
  ingress_security_rules {
    protocol = "1"
    source   = "0.0.0.0/0"
    icmp_options {
      type = 3
      code = 4
    }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_subnet" "api" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.poc.id
  cidr_block        = local.api_cidr
  display_name      = "${var.name}-api"
  dns_label         = "api"
  route_table_id    = oci_core_route_table.api.id
  security_list_ids = [oci_core_security_list.api.id]
}

resource "oci_core_subnet" "workers" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.poc.id
  cidr_block                 = local.worker_cidr
  display_name               = "${var.name}-workers"
  dns_label                  = "workers"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.workers.id
  security_list_ids          = [oci_core_security_list.workers.id]
}

