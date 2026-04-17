import unreal

def get_all_folder_assets():
    """Get all assets in the target folders."""
    target_path = "/Game/BlendSync"
    
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    all_assets = registry.get_assets_by_path(target_path, recursive=True)
    
    folder_assets = {}
    asset_types = {
        unreal.MaterialInstance,
        unreal.Material,
        unreal.StaticMesh,
        unreal.Texture,
        unreal.Texture2D
    }
    
    for asset in all_assets:
        asset_path = asset.get_full_name().split(' ')[-1]
        asset_class = asset.get_class()
        
        # Only track assets of specified types
        for asset_type in asset_types:
            if asset_class.get_name() == asset_type.__name__:
                folder_assets[asset_path] = asset_class.get_name()
                break
    
    return folder_assets

def get_referenced_assets():
    """Get all assets referenced by actors in the current level."""
    referenced = set()
    
    editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    editor_world = editor_subsystem.get_editor_world()
    
    # Get references from each actor
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    all_actors = actor_subsystem.get_all_level_actors()
    
    for actor in all_actors:
        # Check all components of the actor
        components = actor.get_components_by_class(unreal.SceneComponent)
        for component in components:
            try:
                # Check for static mesh components
                if isinstance(component, unreal.StaticMeshComponent):
                    static_mesh = component.static_mesh
                    if static_mesh:
                        mesh_path = static_mesh.get_path_name().split(' ')[-1]
                        referenced.add(mesh_path)
                        
                        # Get mesh materials
                        num_materials = component.get_num_materials()
                        for i in range(num_materials):
                            material = component.get_material(i)
                            if material:
                                material_path = material.get_path_name().split(' ')[-1]
                                referenced.add(material_path)
                                
                                # If it's a material instance, get its parent material
                                if isinstance(material, unreal.MaterialInstance):
                                    parent = material.get_base_material()
                                    if parent:
                                        parent_path = parent.get_path_name().split(' ')[-1]
                                        referenced.add(parent_path)
                                        
                # Check for hierarchical instanced static mesh components
                elif isinstance(component, unreal.HierarchicalInstancedStaticMeshComponent):
                    static_mesh = component.static_mesh
                    if static_mesh:
                        mesh_path = static_mesh.get_path_name().split(' ')[-1]
                        referenced.add(mesh_path)
                        
                        # Get instance materials
                        num_materials = component.get_num_materials()
                        for i in range(num_materials):
                            material = component.get_material(i)
                            if material:
                                material_path = material.get_path_name().split(' ')[-1]
                                referenced.add(material_path)
                                
                                # Get texture references from materials
                                if material:
                                    textures = unreal.EditorMaterialLibrary.get_material_textures(material)
                                    for texture in textures:
                                        if texture:
                                            texture_path = texture.get_path_name().split(' ')[-1]
                                            referenced.add(texture_path)
                
            except Exception as e:
                print(f"Warning: Error processing component: {str(e)}")
    
    return referenced

def should_protect_asset(asset_path, asset_name):
    """
    Determine if an asset should be protected from deletion based on path or name rules.
    Returns True if the asset should be protected, False otherwise.
    """
    # Protected folders
    protected_folders = [
        "/Game/BlendSync/BlendSyncWidget",
        "/Game/BlendSync/MasterMaterials"
    ]
    
    # Check if asset is in protected folders
    for folder in protected_folders:
        if asset_path.startswith(folder):
            print(f"Protected folder - keeping {asset_path}")
            return True
    
    # Check if texture starts with T_BS_
    if asset_name.startswith("T_BS_"):
        print(f"Protected texture prefix - keeping {asset_path}")
        return True
        
    return False

def delete_unused_assets():
    """Delete unused assets in the BlendSync folder and its subfolders."""
    print("\nGathering all assets in folders...")
    folder_assets = get_all_folder_assets()
    print(f"Found {len(folder_assets)} total assets in target folders")
    
    print("\nGathering referenced assets...")
    referenced_assets = get_referenced_assets()
    print(f"Found {len(referenced_assets)} referenced assets")
    
    deleted_count = {
        "MaterialInstance": 0,
        "Material": 0,
        "StaticMesh": 0,
        "Texture": 0,
        "Texture2D": 0
    }
    skipped_count = 0
    protected_count = 0
    
    print("\nProcessing assets...")
    # Process each asset found in the folders
    for asset_path, asset_type in folder_assets.items():
        asset_name = asset_path.split('/')[-1]
        
        # Debug print
        print(f"\nChecking: {asset_path}")
        
        # Check if asset should be protected
        if should_protect_asset(asset_path, asset_name):
            protected_count += 1
            continue
            
        # Check if asset is referenced
        if asset_path in referenced_assets:
            print(f"Referenced - keeping {asset_path}")
            skipped_count += 1
            continue
        
        # If we get here, the asset is not referenced and not protected
        print(f"Not referenced - deleting {asset_path}")
        unreal.EditorAssetLibrary.delete_asset(asset_path)
        deleted_count[asset_type] += 1
    
    print("\nCleanup Results:")
    print("Deleted assets:")
    for asset_type, count in deleted_count.items():
        if count > 0:
            print(f"  {asset_type}: {count}")
    print(f"Referenced assets skipped: {skipped_count}")
    print(f"Protected assets skipped: {protected_count}")

# Main execution
delete_unused_assets()