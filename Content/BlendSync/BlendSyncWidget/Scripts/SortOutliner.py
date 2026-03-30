import unreal

def sort_actors_in_outliner():
    """
    Sorts actors in the Outliner by placing them into:
    - 'Blueprints'
    - 'Meshes'
    - 'Cameras'
    - 'Lighting'
    """

    # Classes that we'll group into "Lighting"
    lighting_classes = [
        unreal.DirectionalLight,
        unreal.ExponentialHeightFog,    # covers environment/height fog
        unreal.SkyLight,
        unreal.SkyAtmosphere,
        unreal.RectLight,
        unreal.PointLight,
        unreal.SpotLight,
        unreal.PostProcessVolume,
        unreal.VolumetricCloud          # Volumetric Cloud
    ]

    # Retrieve all actors in the current level
    all_actors = unreal.EditorLevelLibrary.get_all_level_actors()

    for actor in all_actors:
        actor_class_name = actor.get_class().get_name()

        # 1. If it's a Blueprint-based actor (typical name ends with "_C"), move to "Blueprints"
        #    (This will override any other category if you keep it first.)
        if actor_class_name.endswith("_C"):
            actor.set_folder_path("Blueprints")
            continue

        # 2. If it's a Static Mesh Actor, move it to "Meshes"
        if isinstance(actor, unreal.StaticMeshActor):
            actor.set_folder_path("Meshes")
            continue

        # 3. If it's a Camera Actor, move it to "Cameras"
        if isinstance(actor, unreal.CameraActor):
            actor.set_folder_path("Cameras")
            continue

        # 4. If it's a known "Lighting" class
        if any(isinstance(actor, cls) for cls in lighting_classes):
            actor.set_folder_path("Lighting")
            continue

        # 4b. If it's an HDRIBackdrop (not always in lighting_classes if the HDRI plugin isn’t loaded)
        if actor_class_name == "HDRIBackdrop":
            actor.set_folder_path("Lighting")
            continue

    print("Actors sorted successfully!")

# (Optional) Call the function immediately when this script is run:
sort_actors_in_outliner()
