output "cluster_id" {
  value = oci_containerengine_cluster.poc.id
}
output "worker_configuration" {
  value = {
    node_pool_id       = oci_containerengine_node_pool.e6.id
    shape              = oci_containerengine_node_pool.e6.node_shape
    nodes              = var.node_count
    ocpus_per_node     = var.node_ocpus
    memory_gb_per_node = var.node_memory_gbs
  }
}
output "selected_oke_image" {
  value = {
    id   = local.selected_node_image_id
    name = local.selected_node_image_name
  }
}
output "create_kubeconfig" {
  value = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.poc.id} --region ${var.region} --file $HOME/.kube/eda-e6-demo-config --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT"
}
output "cloud_shell_private_network" {
  description = "Optional Cloud Shell private-network attachment for API access inside the new VCN."
  value = {
    vcn_id      = oci_core_vcn.poc.id
    subnet_id   = oci_core_subnet.workers.id
    subnet_name = oci_core_subnet.workers.display_name
  }
}
