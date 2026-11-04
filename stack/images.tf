# OKE options are region-, Kubernetes-version-, and architecture-filtered by the
# data source in cluster.tf. Also match the full version in the image name, so
# an unfiltered/mismatched result can never silently select a different patch.
locals {
  image_version_pattern = replace(trimprefix(var.kubernetes_version, "v"), ".", "[.]")
  matching_oke_images = {
    for source in data.oci_containerengine_node_pool_option.regional.sources :
    "${try(regex("[0-9]{4}[.][0-9]{2}[.][0-9]{2}", source.source_name), "0000.00.00")}|${source.source_name}|${source.image_id}" => source
    if(
      source.source_type == "IMAGE" &&
      can(regex("(?i)^Oracle-Linux-${var.node_os_major_version}([.-]|$)", source.source_name)) &&
      can(regex("(?i)(^|[-_])OKE[-_]${local.image_version_pattern}([-_]|$)", source.source_name)) &&
      !can(regex("(?i)(aarch64|arm64|gpu)", source.source_name))
    )
  }

  # Prefer the most recent YYYY.MM.DD image build. Name and OCID break ties
  # deterministically. No arbitrary platform-image fallback is allowed.
  automatic_oke_image    = try(local.matching_oke_images[reverse(sort(keys(local.matching_oke_images)))[0]], null)
  selected_node_image_id = var.node_image_ocid != "" ? var.node_image_ocid : try(local.automatic_oke_image.image_id, "")
  selected_node_image_name = try(one([
    for source in data.oci_containerengine_node_pool_option.regional.sources : source.source_name
    if source.image_id == local.selected_node_image_id
  ]), null)
}
