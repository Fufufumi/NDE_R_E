import unreal

def assign_materials_to_static_mesh_assets():
    """
    Assigns materials from Static Mesh Components to the corresponding Static Mesh assets.
    Skips assignment if the current material is the same as the assigned material.
    """
    # Get all actors in the open level
    actors = unreal.EditorLevelLibrary.get_all_level_actors()

    # Iterate over each actor
    for actor in actors:
        # Check if the actor is a Static Mesh Actor
        if actor.get_class().get_name() == "StaticMeshActor":
            static_mesh_component = actor.static_mesh_component
            if not static_mesh_component:
                unreal.log_warning(f"Actor {actor.get_name()} has no Static Mesh Component, skipping.")
                continue

            # Get the assigned Static Mesh asset
            static_mesh = static_mesh_component.static_mesh
            if not static_mesh:
                unreal.log_warning(f"Actor {actor.get_name()} has no Static Mesh assigned, skipping.")
                continue

            # Get the materials assigned to the Static Mesh Component
            materials = static_mesh_component.get_materials()

            # Assign materials to the Static Mesh asset
            for index, material in enumerate(materials):
                if material:
                    # Check if the current material is the same as the assigned material
                    current_material = static_mesh.get_material(index)
                    if current_material and current_material.get_path_name() == material.get_path_name():
                        unreal.log(f"Material at index {index} is already assigned for {static_mesh.get_name()}, skipping.")
                        continue
                    static_mesh.set_material(index, material)

            # Save changes to the Static Mesh asset
            package_name = static_mesh.get_outer().get_path_name()
            try:
                static_mesh.modify()
                if unreal.EditorAssetLibrary.save_asset(package_name):
                    unreal.log(f"Saved asset: {package_name} with updated materials.")
                else:
                    unreal.log_warning(f"Failed to save asset: {package_name}.")
            except Exception as e:
                unreal.log_error(f"Error saving asset {package_name}: {e}")

# Call the function to assign materials
assign_materials_to_static_mesh_assets()
