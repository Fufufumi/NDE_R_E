import unreal
import os

def get_selected_static_meshes():
    """
    Get static meshes from selected actors and directly selected assets
    Returns a set of unique static mesh paths
    """
    selected_meshes = set()

    # Get selected actors in the viewport
    selection = unreal.EditorLevelLibrary.get_selected_level_actors()

    # Process selected actors
    for actor in selection:
        # Check if it's a static mesh actor
        if isinstance(actor, unreal.StaticMeshActor):
            static_mesh_component = actor.static_mesh_component
            if static_mesh_component:
                static_mesh = static_mesh_component.static_mesh
                if static_mesh:
                    selected_meshes.add(static_mesh.get_path_name())
        # Check if it has static mesh components
        else:
            components = actor.get_components_by_class(unreal.StaticMeshComponent)
            for component in components:
                if component and component.static_mesh:
                    selected_meshes.add(component.static_mesh.get_path_name())

    # Get selected assets in content browser
    selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()
    for asset in selected_assets:
        if isinstance(asset, unreal.StaticMesh):
            selected_meshes.add(asset.get_path_name())

    return selected_meshes

def get_mesh_materials_map(mesh_path):
    """
    Get a mapping of material slots and their materials for a static mesh
    Returns: dict with slot indices as keys and material paths as values
    """
    mesh_asset = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if not mesh_asset or not isinstance(mesh_asset, unreal.StaticMesh):
        return {}

    materials_map = {}

    # Get materials for all sections in LOD 0
    for section_index in range(mesh_asset.get_num_sections(0)):
        material = mesh_asset.get_material(section_index)
        if material:
            material_path = material.get_path_name()
            materials_map[section_index] = material_path

    return materials_map

def get_material_textures(material_path):
    """
    Get all textures used by a material instance
    Returns: dict mapping texture parameter names to texture paths
    """
    material = unreal.EditorAssetLibrary.load_asset(material_path)
    if not material:
        return {}

    texture_map = {}

    try:
        # Get material property override data
        if isinstance(material, unreal.MaterialInstanceConstant):
            # Get texture parameter values
            texture_overrides = material.texture_parameter_values
            for override in texture_overrides:
                param_name = override.parameter_info.name
                texture = override.parameter_value
                if texture:
                    texture_map[param_name] = texture.get_path_name()

            # Check parent material if it's an instance
            parent = material.parent
            if parent and isinstance(parent, unreal.MaterialInstanceConstant):
                parent_textures = get_material_textures(parent.get_path_name())
                # Only add parent textures that aren't overridden in the instance
                for param_name, texture_path in parent_textures.items():
                    if param_name not in texture_map:
                        texture_map[param_name] = texture_path

    except Exception as e:
        unreal.log_warning(f"Error getting textures from material {material_path}: {str(e)}")

    return texture_map

def copy_to_library(source_path, target_path):
    """
    Copy asset to library without deleting source
    Returns: Path of the copied asset if successful, None otherwise
    """
    try:
        # Load source asset
        source_asset = unreal.EditorAssetLibrary.load_asset(source_path)
        if not source_asset:
            unreal.log_error(f"Source asset cannot be loaded: {source_path}")
            return None

        # Make sure the target directory exists
        target_dir = os.path.dirname(target_path)
        if not unreal.EditorAssetLibrary.does_directory_exist(target_dir):
            unreal.EditorAssetLibrary.make_directory(target_dir)

        # Delete old asset if it exists
        if unreal.EditorAssetLibrary.does_asset_exist(target_path):
            unreal.EditorAssetLibrary.delete_asset(target_path)

        # Copy source to target
        success = unreal.EditorAssetLibrary.duplicate_asset(source_path, target_path)
        if success:
            unreal.log(f"Successfully copied {source_path} to {target_path}")
            return target_path
        else:
            unreal.log_error(f"Failed to copy {source_path} to {target_path}")
            return None
    except Exception as e:
        unreal.log_error(f"Error copying asset: {str(e)}")
        return None

def find_matching_asset_in_library(asset_name, library_path):
    """
    Find an asset with the given name in the library or its subfolders
    Returns: Full path of the matching asset if found, None otherwise
    """
    library_assets = unreal.EditorAssetLibrary.list_assets(library_path, recursive=True)
    for asset_path in library_assets:
        if os.path.splitext(os.path.basename(asset_path))[0] == asset_name:
            return asset_path
    return None

def move_textures_to_library(textures, target_dir):
    """
    Move textures to the library textures folder and return mapping of old to new paths
    """
    texture_path_map = {}
    textures_dir = f"{target_dir}/Textures"

    # Ensure textures directory exists
    if not unreal.EditorAssetLibrary.does_directory_exist(textures_dir):
        unreal.EditorAssetLibrary.make_directory(textures_dir)

    for param_name, texture_path in textures.items():
        texture_name = os.path.splitext(os.path.basename(texture_path))[0]
        new_texture_path = f"{textures_dir}/{texture_name}"

        try:
            # Only move if source and target are different
            if texture_path != new_texture_path:
                # Check if source texture exists
                if not unreal.EditorAssetLibrary.does_asset_exist(texture_path):
                    unreal.log_warning(f"Source texture not found: {texture_path}")
                    continue

                # If texture already exists in target location, use it
                if unreal.EditorAssetLibrary.does_asset_exist(new_texture_path):
                    texture_path_map[texture_path] = new_texture_path
                    continue

                # Move texture to new location using duplicate_asset instead of rename_asset
                success = unreal.EditorAssetLibrary.duplicate_asset(texture_path, new_texture_path)

                if success:
                    # Delete the source after successful duplication
                    unreal.EditorAssetLibrary.delete_asset(texture_path)
                    unreal.log(f"Successfully moved texture from {texture_path} to {new_texture_path}")
                    texture_path_map[texture_path] = new_texture_path
                else:
                    unreal.log_error(f"Failed to move texture: {texture_path}")
            else:
                # Texture is already in the correct location
                texture_path_map[texture_path] = texture_path

        except Exception as e:
            unreal.log_error(f"Error moving texture {texture_path}: {str(e)}")

    return texture_path_map

def update_material_texture_references(material_path, texture_path_map):
    """
    Update material's texture references to point to new locations
    """
    material = unreal.EditorAssetLibrary.load_asset(material_path)
    if not material or not isinstance(material, unreal.MaterialInstanceConstant):
        return False

    try:
        # For MaterialInstanceConstant, we need to work with TextureParameterValues
        texture_params = material.texture_parameter_values
        for param in texture_params:
            current_texture = param.parameter_value
            if current_texture:
                current_path = current_texture.get_path_name()
                if current_path in texture_path_map:
                    # Load new texture
                    new_texture = unreal.EditorAssetLibrary.load_asset(texture_path_map[current_path])
                    if new_texture:
                        # Update the parameter value with the new texture
                        param.parameter_value = new_texture

        # Force update of the material instance
        material.post_edit_change()

        # Save the material with updated references
        unreal.EditorAssetLibrary.save_asset(material_path)
        return True
    except Exception as e:
        unreal.log_error(f"Error updating texture references in material {material_path}: {str(e)}")
        return False

def assign_materials_to_mesh(mesh_path, materials_map, material_folder):
    """
    Assign materials to the mesh's slots
    """
    try:
        mesh_asset = unreal.EditorAssetLibrary.load_asset(mesh_path)
        if not mesh_asset or not isinstance(mesh_asset, unreal.StaticMesh):
            return False

        success = True
        for slot_index, material_path in materials_map.items():
            material_name = os.path.splitext(os.path.basename(material_path))[0]
            new_material_path = f"{material_folder}/{material_name}"

            material = unreal.EditorAssetLibrary.load_asset(new_material_path)
            if material:
                mesh_asset.set_material(slot_index, material)
            else:
                unreal.log_error(f"Failed to load material: {new_material_path}")
                success = False

        # Save the mesh with new material assignments
        if success:
            unreal.EditorAssetLibrary.save_asset(mesh_path)
            unreal.log(f"Successfully reassigned materials for {mesh_path}")

        return success
    except Exception as e:
        unreal.log_error(f"Error assigning materials to mesh: {str(e)}")
        return False

def add_lib_suffix(path):
    """
    Add _LIB suffix to asset name, preserving only the base name without path
    """
    base_name = os.path.splitext(os.path.basename(path))[0]
    return f"{base_name}_ALIB"

def move_texture_to_library(texture_path, target_dir):
    """
    Move a texture to the library folder, handle redirectors and overwrite if needed
    Returns: New texture path if successful, None otherwise
    """
    try:
        # Skip if texture doesn't exist
        if not unreal.EditorAssetLibrary.does_asset_exist(texture_path):
            return None

        # Setup target path
        texture_name = os.path.splitext(os.path.basename(texture_path))[0]
        new_texture_path = f"{target_dir}/{texture_name}"

        # If texture already exists at target, delete it
        if unreal.EditorAssetLibrary.does_asset_exist(new_texture_path):
            unreal.EditorAssetLibrary.delete_asset(new_texture_path)

        # Move the texture
        success = unreal.EditorAssetLibrary.rename_asset(texture_path, new_texture_path)
        if success:
            unreal.log(f"Successfully moved texture from {texture_path} to {new_texture_path}")

            # Fix up redirectors
            unreal.EditorLoadingAndSavingUtils.fix_up_redirectors_in_path(os.path.dirname(texture_path))
            return new_texture_path

    except Exception as e:
        unreal.log_error(f"Error moving texture {texture_path}: {str(e)}")

    return None

def sync_assets():
    """
    Main function to sync selected static meshes between BlenderSyncExchange and Asset_Library
    """
    source_dir = "/Game/BlendSyncExchange"
    target_dir = "/Game/Asset_Library"
    meshes_dir = f"{target_dir}/Meshes"
    materials_dir = f"{target_dir}/Materials"
    textures_dir = f"{target_dir}/Textures"

    # Ensure required directories exist
    for dir_path in [meshes_dir, materials_dir, textures_dir]:
        if not unreal.EditorAssetLibrary.does_directory_exist(dir_path):
            unreal.EditorAssetLibrary.make_directory(dir_path)

    # Get selected static meshes
    selected_meshes = get_selected_static_meshes()
    if not selected_meshes:
        unreal.log_warning("No static meshes selected. Please select some static mesh actors or assets.")
        return

    # Get all assets in source directory
    source_assets = unreal.EditorAssetLibrary.list_assets(source_dir, recursive=True)

    # First move all textures from BlenderSyncExchange
    moved_textures = {}
    for asset_path in source_assets:
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if isinstance(asset, unreal.Texture2D):
            new_path = move_texture_to_library(asset_path, textures_dir)
            if new_path:
                moved_textures[asset_path] = new_path

    # Track statistics
    copied_count = 0
    validated_count = 0
    failed_count = 0
    copied_materials_count = 0
    copied_textures_count = len(moved_textures)

    # Process each selected mesh
    for mesh_path in selected_meshes:
        mesh_name = os.path.splitext(os.path.basename(mesh_path))[0]

        # Find matching source asset
        source_path = None
        for asset_path in source_assets:
            if os.path.splitext(os.path.basename(asset_path))[0] == mesh_name:
                source_path = asset_path
                break

        if not source_path:
            unreal.log_warning(f"No matching asset found in BlenderSyncExchange for {mesh_name}")
            continue

        # Try to find matching asset in library
        existing_asset_path = find_matching_asset_in_library(mesh_name, target_dir)

        # Get materials map before copying
        materials_map = get_mesh_materials_map(source_path)

        if existing_asset_path:
            # Update existing asset
            target_path = existing_asset_path
            target_folder = os.path.dirname(target_path)

            if copy_to_library(source_path, target_path):
                copied_count += 1

                # Handle materials for existing asset
                if materials_map:
                    for slot_index, material_path in materials_map.items():
                        material_name = os.path.splitext(os.path.basename(material_path))[0]
                        new_material_path = f"{materials_dir}/{material_name}"

                        if copy_to_library(material_path, new_material_path):
                            copied_materials_count += 1
                        else:
                            failed_count += 1

                    assign_materials_to_mesh(target_path, materials_map, materials_dir)
            else:
                failed_count += 1

        # Create copy in Meshes folder with _LIB suffix
        validated_mesh_path = f"{meshes_dir}/{add_lib_suffix(source_path)}"

        if copy_to_library(source_path, validated_mesh_path):
            validated_count += 1

            # Handle materials for library copy
            if materials_map:
                for slot_index, material_path in materials_map.items():
                    lib_material_path = f"{materials_dir}/{add_lib_suffix(material_path)}"

                    if copy_to_library(material_path, lib_material_path):
                        copied_materials_count += 1
                    else:
                        failed_count += 1

                # Update material map for library mesh
                validated_materials_map = {
                    slot_index: f"{materials_dir}/{add_lib_suffix(material_path)}"
                    for slot_index, material_path in materials_map.items()
                }
                assign_materials_to_mesh(validated_mesh_path, validated_materials_map, materials_dir)
        else:
            failed_count += 1

    # Save all assets
    unreal.EditorAssetLibrary.save_directory(target_dir)
    unreal.EditorAssetLibrary.save_directory(meshes_dir)
    unreal.EditorAssetLibrary.save_directory(materials_dir)

    # Report results
    unreal.log(f"""Asset sync completed:
    - Selected meshes processed: {len(selected_meshes)}
    - Updated in library: {copied_count} meshes
    - Created in Meshes: {validated_count} meshes
    - Copied materials: {copied_materials_count}
    - Copied textures: {copied_textures_count}
    - Failed operations: {failed_count}""")

    # Rest of the sync_assets function remains the same...


    # Process each selected mesh
    for mesh_path in selected_meshes:
        mesh_name = os.path.splitext(os.path.basename(mesh_path))[0]

        # Find matching source asset
        source_path = None
        for asset_path in source_assets:
            if os.path.splitext(os.path.basename(asset_path))[0] == mesh_name:
                source_path = asset_path
                break

        if not source_path:
            unreal.log_warning(f"No matching asset found in BlenderSyncExchange for {mesh_name}")
            continue

        # Try to find matching asset in library
        existing_asset_path = find_matching_asset_in_library(mesh_name, target_dir)

        # Get materials map before copying
        materials_map = get_mesh_materials_map(source_path)

        if existing_asset_path:
            # Update existing asset
            target_path = existing_asset_path
            target_folder = os.path.dirname(target_path)

            if copy_to_library(source_path, target_path):
                copied_count += 1

                # Handle materials and textures for existing asset
                if materials_map:
                    for slot_index, material_path in materials_map.items():
                        material_name = os.path.splitext(os.path.basename(material_path))[0]
                        new_material_path = f"{target_folder}/{material_name}"

                        if copy_to_library(material_path, new_material_path):
                            copied_materials_count += 1

                            # Handle textures for this material
                            textures = get_material_textures(new_material_path)
                            if textures:
                                # First get all textures to be moved
                                texture_path_map = move_textures_to_library(textures, target_dir)
                                copied_textures_count += len(texture_path_map)

                                # Now update the material instance to use the new texture locations
                                if texture_path_map:
                                    success = update_material_texture_references(new_material_path, texture_path_map)
                                    if not success:
                                        unreal.log_error(f"Failed to update texture references for {new_material_path}")
                                    else:
                                        unreal.log(f"Successfully updated texture references for {new_material_path}")
                        else:
                            failed_count += 1

                    assign_materials_to_mesh(target_path, materials_map, target_folder)
            else:
                failed_count += 1

        # Create validated copy with _LIB suffix
        validated_mesh_path = f"{validated_dir}/{add_lib_suffix(source_path)}"

        if copy_to_library(source_path, validated_mesh_path):
            validated_count += 1

            # Handle materials and textures for validated copy
            if materials_map:
                for slot_index, material_path in materials_map.items():
                    validated_material_path = f"{validated_dir}/{add_lib_suffix(material_path)}"

                    if copy_to_library(material_path, validated_material_path):
                        copied_materials_count += 1

                        # Handle textures for validated material
                        textures = get_material_textures(validated_material_path)
                        if textures:
                            texture_path_map = move_textures_to_library(textures, target_dir)
                            copied_textures_count += len(texture_path_map)
                            update_material_texture_references(validated_material_path, texture_path_map)
                    else:
                        failed_count += 1

                # Update material map for validated mesh
                validated_materials_map = {
                    slot_index: f"{validated_dir}/{add_lib_suffix(material_path)}"
                    for slot_index, material_path in materials_map.items()
                }
                assign_materials_to_mesh(validated_mesh_path, validated_materials_map, validated_dir)
        else:
            failed_count += 1

    # Save all assets
    unreal.EditorAssetLibrary.save_directory(target_dir)
    unreal.EditorAssetLibrary.save_directory(validated_dir)

    # Report results
    unreal.log(f"""Asset sync completed:
    - Selected meshes processed: {len(selected_meshes)}
    - Updated in library: {copied_count} meshes
    - Created in Validated: {validated_count} meshes
    - Copied materials: {copied_materials_count}
    - Copied textures: {copied_textures_count}
    - Failed operations: {failed_count}""")

# Direct execution
sync_assets()