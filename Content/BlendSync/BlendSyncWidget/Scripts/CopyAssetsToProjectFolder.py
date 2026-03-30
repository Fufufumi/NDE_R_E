import unreal

def fix_redirectors_in_folder(folder_path):
    """
    Fixes redirectors in the given folder by attempting to resolve them.
    """
    unreal.log(f"Fixing redirectors in folder: {folder_path}")

    all_assets = unreal.EditorAssetLibrary.list_assets(folder_path, recursive=True, include_folder=False)
    redirectors = [
        asset for asset in all_assets
        if "Redirector" in unreal.EditorAssetLibrary.find_asset_data(asset).get_class().get_name()
    ]

    processed_redirectors = 0
    failed_redirectors = 0

    if redirectors:
        for redirector_path in redirectors:
            try:
                asset_data = unreal.EditorAssetLibrary.find_asset_data(redirector_path)
                if asset_data:
                    unreal.EditorAssetLibrary.save_asset(redirector_path, False)
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
        if isinstance(material, unreal.MaterialInstanceConstant):
            param_names = []
            try:
                param_names = material.get_editor_property("texture_parameter_values")
            except:
                pass

            for param in param_names:
                try:
                    texture_value = material.get_editor_property(param.parameter_info.name)
                    if isinstance(texture_value, unreal.Texture):
                        textures.add(texture_value)
                except:
                    pass

            parent = material.get_base_material()
            if parent:
                textures.update(get_material_texture_parameters(parent))

        elif isinstance(material, unreal.Material):
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

def ensure_folder_exists(folder_path):
    """
    Ensures the specified folder exists, creates it if it doesn't.
    """
    folder_path = folder_path.rstrip('/')
    if not unreal.EditorAssetLibrary.does_directory_exist(folder_path):
        if unreal.EditorAssetLibrary.make_directory(folder_path):
            unreal.log(f"Created folder: {folder_path}")
        else:
            unreal.log_error(f"Failed to create folder: {folder_path}")
            return False
    return True

def get_destination_path(asset, base_folder):
    """
    Determines the appropriate destination path based on asset type.
    """
    asset_name = unreal.Paths.get_base_filename(asset.get_path_name())

    if isinstance(asset, unreal.StaticMesh):
        return f"{base_folder}/Meshes/{asset_name}"
    elif isinstance(asset, (unreal.Material, unreal.MaterialInstanceConstant)):
        return f"{base_folder}/Materials/{asset_name}"
    elif isinstance(asset, unreal.Texture):
        return f"{base_folder}/Textures/{asset_name}"
    else:
        return f"{base_folder}/Other/{asset_name}"

def copy_assets_to_folder(base_folder):
    """
    Copies all assets used in the currently open level to type-specific folders.
    """
    actor_utility = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_utility.get_all_level_actors()

    if not all_actors:
        unreal.log_warning("No actors in the current level.")
        return

    used_assets = set()
    asset_replacement_map = {}

    # Create necessary folders
    folders = [f"{base_folder}/{subfolder}" for subfolder in ["Meshes", "Materials", "Textures", "Other"]]
    for folder in folders:
        if not ensure_folder_exists(folder):
            return

    # Collect assets
    for actor in all_actors:
        static_mesh_component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if static_mesh_component:
            static_mesh = static_mesh_component.get_editor_property("static_mesh")
            if static_mesh:
                used_assets.add(static_mesh)

            materials = static_mesh_component.get_materials()
            for material in materials:
                if material:
                    used_assets.add(material)
                    textures = get_material_texture_parameters(material)
                    used_assets.update(textures)

    # Copy assets
    for asset in used_assets:
        if not asset:
            continue

        asset_path = asset.get_path_name()
        destination_path = get_destination_path(asset, base_folder)

        if unreal.EditorAssetLibrary.does_asset_exist(destination_path):
            unreal.log(f"Asset '{asset.get_name()}' already exists. Using existing asset.")
            asset_replacement_map[asset_path] = destination_path
            continue

        copied_asset = unreal.EditorAssetLibrary.duplicate_asset(asset_path, destination_path)
        if copied_asset:
            unreal.log(f"Copied asset '{asset.get_name()}' to {destination_path}.")
            asset_replacement_map[asset_path] = destination_path
        else:
            unreal.log_error(f"Failed to copy asset '{asset.get_name()}'.")

    # Update references
    for actor in all_actors:
        static_mesh_component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if static_mesh_component:
            static_mesh = static_mesh_component.get_editor_property("static_mesh")
            if static_mesh:
                original_path = static_mesh.get_path_name()
                if original_path in asset_replacement_map:
                    new_path = asset_replacement_map[original_path]
                    new_static_mesh = unreal.EditorAssetLibrary.load_asset(new_path)
                    if new_static_mesh:
                        static_mesh_component.set_editor_property("static_mesh", new_static_mesh)

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
    base_folder = "/Game/BlendSync"
    unreal.log("Starting asset copying process...")
    copy_assets_to_folder(base_folder)
    fix_redirectors_in_folder("/Game")
    unreal.log("Asset copying process completed.")

# Execute the script
main()