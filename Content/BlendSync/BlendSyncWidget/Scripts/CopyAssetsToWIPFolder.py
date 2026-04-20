import unreal

def fix_redirectors_in_folder(folder_path):
    """
    Fixes redirectors in the given folder by attempting to resolve them.
    """
    unreal.log(f"Fixing redirectors in folder: {folder_path}")

    # List all assets in the folder
    all_assets = unreal.EditorAssetLibrary.list_assets(folder_path, recursive=True, include_folder=False)

    # Filter for redirectors
    redirectors = [
        asset for asset in all_assets
        if "Redirector" in unreal.EditorAssetLibrary.find_asset_data(asset).get_class().get_name()
    ]

    processed_redirectors = 0
    failed_redirectors = 0

    if redirectors:
        # Resolve each redirector
        for redirector_path in redirectors:
            try:
                # Try to load the asset
                asset_data = unreal.EditorAssetLibrary.find_asset_data(redirector_path)

                if asset_data:
                    # Try to permanently resolve the redirector
                    unreal.EditorAssetLibrary.save_asset(redirector_path, False)

                    # Optional: delete if save doesn't work
                    if unreal.EditorAssetLibrary.does_asset_exist(redirector_path):
                        unreal.EditorAssetLibrary.delete_asset(redirector_path)

                    processed_redirectors += 1
                    unreal.log(f"Processed redirector: {redirector_path}")
                else:
                    failed_redirectors += 1
                    unreal.log_warning(f"Could not process redirector: {redirector_path}")
            except Exception as e:
                failed_redirectors += 1
                unreal.log_error(f"Error processing redirector {redirector_path}: {str(e)}")

        unreal.log(f"Processed {processed_redirectors} redirectors in folder {folder_path}.")
        if failed_redirectors > 0:
            unreal.log_warning(f"Failed to process {failed_redirectors} redirectors.")
    else:
        unreal.log(f"No redirectors to fix in folder {folder_path}.")

def get_material_texture_parameters(material):
    """
    Extracts all texture references from a material by checking its parameters.
    """
    textures = set()

    try:
        # Handle material instances
        if isinstance(material, unreal.MaterialInstanceConstant):
            # Get all texture parameter names
            param_names = []
            try:
                param_names = material.get_editor_property("texture_parameter_values")
            except:
                pass

            # Try to get parameter values
            for param in param_names:
                try:
                    texture_value = material.get_editor_property(param.parameter_info.name)
                    if isinstance(texture_value, unreal.Texture):
                        textures.add(texture_value)
                except:
                    pass

            # Get parent material textures
            parent = material.get_base_material()
            if parent:
                textures.update(get_material_texture_parameters(parent))

        # Handle base materials
        elif isinstance(material, unreal.Material):
            # Try to get texture parameters directly
            try:
                for param_name in material.get_static_parameter_names():
                    param_value = material.get_static_parameter_value(param_name)
                    if isinstance(param_value, unreal.Texture):
                        textures.add(param_value)
            except:
                pass

    except Exception as e:
        unreal.log_warning(f"Error extracting textures from material {material.get_name()}: {str(e)}")

    return textures

def copy_assets_to_folder(destination_folder):
    """
    Copies all assets used in the currently open level to the specified destination folder,
    then replaces original assets with their copies (or existing assets in the destination folder).
    """
    # Get reference to the Editor Actor Utilities Subsystem
    actor_utility = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    # Get all actors in the open level
    all_actors = actor_utility.get_all_level_actors()
    if not all_actors:
        unreal.log_warning("No actors in the current level.")
        return

    # Identify assets used by objects in the level
    used_assets = set()
    asset_replacement_map = {}

    for actor in all_actors:
        static_mesh_component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if static_mesh_component:
            # Add Static Mesh
            static_mesh = static_mesh_component.get_editor_property("static_mesh")
            if static_mesh:
                used_assets.add(static_mesh)

            # Add Materials and their textures
            materials = static_mesh_component.get_materials()
            for material in materials:
                if material:
                    used_assets.add(material)
                    # Add textures used in the material
                    textures = get_material_texture_parameters(material)
                    used_assets.update(textures)

    # Ensure the destination folder exists
    destination_folder = destination_folder.rstrip('/')
    if not unreal.EditorAssetLibrary.does_directory_exist(destination_folder):
        if unreal.EditorAssetLibrary.make_directory(destination_folder):
            unreal.log(f"Created folder: {destination_folder}")
        else:
            unreal.log_error(f"Failed to create folder: {destination_folder}")
            return

    # Check and copy assets
    for asset in used_assets:
        if not asset:  # Skip if asset is None
            continue

        asset_path = asset.get_path_name()
        asset_name = unreal.Paths.get_base_filename(asset_path)
        destination_path = f"{destination_folder}/{asset_name}"

        # If the asset already exists in the destination folder, use it
        if unreal.EditorAssetLibrary.does_asset_exist(destination_path):
            unreal.log(f"Asset '{asset_name}' already exists in folder {destination_folder}. Using existing asset.")
            asset_replacement_map[asset_path] = destination_path
            continue

        # Copy the asset
        copied_asset = unreal.EditorAssetLibrary.duplicate_asset(asset_path, destination_path)
        if copied_asset:
            unreal.log(f"Copied asset '{asset_name}' to folder {destination_folder}.")
            asset_replacement_map[asset_path] = destination_path
        else:
            unreal.log_error(f"Failed to copy asset '{asset_name}'.")

    # Replace original assets with their copies or existing equivalents
    for actor in all_actors:
        static_mesh_component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if static_mesh_component:
            # Replace Static Mesh
            static_mesh = static_mesh_component.get_editor_property("static_mesh")
            if static_mesh:
                original_path = static_mesh.get_path_name()
                if original_path in asset_replacement_map:
                    new_path = asset_replacement_map[original_path]
                    new_static_mesh = unreal.EditorAssetLibrary.load_asset(new_path)
                    if new_static_mesh:
                        static_mesh_component.set_editor_property("static_mesh", new_static_mesh)

            # Replace Materials
            materials = static_mesh_component.get_materials()
            for i, material in enumerate(materials):
                if material:
                    original_path = material.get_path_name()
                    if original_path in asset_replacement_map:
                        new_path = asset_replacement_map[original_path]
                        new_material = unreal.EditorAssetLibrary.load_asset(new_path)
                        if new_material:
                            static_mesh_component.set_material(i, new_material)

def main():
    """
    Main execution method.
    """
    destination_folder = "/Game/BlendSyncExchange"
    unreal.log("Starting asset copying process...")

    # Copy assets used in the level to the destination folder
    copy_assets_to_folder(destination_folder)

    # Fix redirectors
    fix_redirectors_in_folder("/Game")

    unreal.log("Asset copying process completed.")

# Execute the script
main()