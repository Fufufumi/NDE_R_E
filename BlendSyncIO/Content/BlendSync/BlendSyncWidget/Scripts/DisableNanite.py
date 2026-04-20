import unreal

def disable_nanite_on_selected():
    """
    Disables Nanite for selected Static Mesh assets and Static Mesh components of selected actors in Unreal Engine 5.
    """
    # Counters for reporting
    nanite_disabled_count = 0
    non_static_mesh_count = 0
    actors_processed = 0

    # Get the currently selected assets in the Content Browser
    selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()

    # Get the currently selected actors in the Level Editor
    selected_actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors()

    # Process selected assets
    for asset in selected_assets:
        if isinstance(asset, unreal.StaticMesh):
            try:
                # Access Nanite settings and disable Nanite
                nanite_settings = asset.get_editor_property("nanite_settings")
                if nanite_settings and nanite_settings.get_editor_property("enabled"):
                    nanite_settings.set_editor_property("enabled", False)
                    asset.modify()
                    unreal.EditorAssetLibrary.save_asset(asset.get_path_name())
                    unreal.log(f"Disabled Nanite for asset: {asset.get_name()}")
                    nanite_disabled_count += 1
                else:
                    unreal.log(f"Nanite is already disabled for asset: {asset.get_name()}")
            except Exception as e:
                unreal.log_error(f"Error disabling Nanite for asset {asset.get_name()}: {e}")
        else:
            non_static_mesh_count += 1

    # Process selected actors
    for actor in selected_actors:
        static_mesh_component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if static_mesh_component:
            static_mesh = static_mesh_component.get_editor_property("static_mesh")
            if static_mesh:
                try:
                    # Access Nanite settings and disable Nanite
                    nanite_settings = static_mesh.get_editor_property("nanite_settings")
                    if nanite_settings and nanite_settings.get_editor_property("enabled"):
                        nanite_settings.set_editor_property("enabled", False)
                        static_mesh.modify()
                        unreal.EditorAssetLibrary.save_asset(static_mesh.get_path_name())
                        unreal.log(f"Disabled Nanite for Static Mesh used by actor: {actor.get_name()}")
                        nanite_disabled_count += 1
                    else:
                        unreal.log(f"Nanite is already disabled for Static Mesh used by actor: {actor.get_name()}")
                except Exception as e:
                    unreal.log_error(f"Error disabling Nanite for mesh in actor {actor.get_name()}: {e}")
            else:
                unreal.log_warning(f"Actor '{actor.get_name()}' does not have a Static Mesh assigned.")
        else:
            unreal.log_warning(f"Actor '{actor.get_name()}' does not have a Static Mesh Component.")
        actors_processed += 1

    # Summary log
    unreal.log(f"Nanite disabled on {nanite_disabled_count} Static Mesh(es).")
    unreal.log(f"Processed {actors_processed} actor(s).")
    if non_static_mesh_count > 0:
        unreal.log_warning(f"{non_static_mesh_count} non-Static Mesh assets were ignored.")

# Execute the function
disable_nanite_on_selected()
