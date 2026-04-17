import unreal
import os
import json
from pathlib import Path

class BlenderSyncUEExport:
    def __init__(self):
        self.export_directory = None
        # Get subsystems
        self.editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.editor_actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def setup_export_path(self):
        """Setup and validate export path"""
        project_dir = unreal.Paths.project_dir()
        self.export_directory = os.path.join(project_dir, "BlendSyncIO", "Blender")

        if not os.path.exists(self.export_directory):
            os.makedirs(self.export_directory)
            unreal.log(f"Created export directory: {self.export_directory}")

    def is_material_in_blendersync_folder(self, material):
        """Check if material is located in BlenderSync folders"""
        if not material:
            return False

        material_path = material.get_path_name()
        
        # Check for all possible BlenderSync material locations
        blendersync_paths = [
            "/Game/BlendSync/Materials/",      # Material instances from import script
            "/Game/BlendSync/MasterMaterials/", # Master materials from import script  
            "/BlenderSyncWidget/MasterMaterials/" # Widget master materials
        ]

        return any(path in material_path for path in blendersync_paths)

    def _get_static_mesh_asset(self, actor):
        """Return the StaticMesh asset for the given actor, if any."""
        if not isinstance(actor, unreal.StaticMeshActor):
            return None

        component = actor.static_mesh_component
        if not component:
            return None

        return component.static_mesh

    def _get_export_name(self, actor):
        """Determine the filename/node name we want for this actor's export."""
        export_name = None
        if isinstance(actor, unreal.StaticMeshActor):
            component = actor.static_mesh_component
            if component and component.static_mesh:
                export_name = component.static_mesh.get_name()

        if not export_name:
            try:
                export_name = actor.get_actor_label()
            except Exception:
                export_name = None

        if not export_name:
            export_name = actor.get_name()

        return export_name

    def _get_actor_label_name(self, actor):
        """Return a human-friendly actor label, falling back to internal name."""
        try:
            label = actor.get_actor_label()
            if label:
                return label
        except Exception:
            pass
        return actor.get_name()

    def _build_instance_entry(self, actor, source_actor_name, source_object_name, static_mesh):
        """Create a manifest entry for an instance of an already-exported asset."""
        component = actor.static_mesh_component
        if not component:
            return None

        world_transform = component.get_world_transform()
        translation = world_transform.translation
        rotation = world_transform.rotation.rotator()
        scale = world_transform.scale3d

        object_name = source_object_name or source_actor_name

        entry = {
            "name": self._get_actor_label_name(actor),
            "source_actor": source_actor_name,
            "source_object_name": object_name,
            "asset_path": static_mesh.get_path_name() if static_mesh else "",
            "fbx_file": f"{object_name}.fbx",
            "transform": {
                "location_cm": [
                    float(translation.x),
                    float(translation.y),
                    float(translation.z),
                ],
                "rotation_deg": {
                    "pitch": float(rotation.pitch),
                    "yaw": float(rotation.yaw),
                    "roll": float(rotation.roll),
                },
                "scale": [
                    float(scale.x),
                    float(scale.y),
                    float(scale.z),
                ]
            }
        }
        return entry

    def _write_scene_manifest(self, instances, material_params=None):
        """Write or clear the scene manifest file describing instanced actors and material parameters."""
        scene_path = os.path.join(self.export_directory, "scene.json")

        if not instances:
            if os.path.exists(scene_path):
                try:
                    os.remove(scene_path)
                    unreal.log("Removed stale scene.json (no instances detected).")
                except Exception as e:
                    unreal.log_warning(f"Failed to remove stale scene.json: {e}")
            return

        manifest = {
            "version": 1,
            "coordinate_system": "unreal",
            "units": "centimeters",
            "instances": instances
        }

        # Add material parameters if available
        if material_params:
            manifest["materials"] = material_params
            unreal.log(f"Added {len(material_params)} material(s) with parameters to manifest")

        try:
            with open(scene_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
            unreal.log(f"Wrote scene manifest with {len(instances)} instanced actor(s) to {scene_path}")
        except Exception as e:
            unreal.log_warning(f"Failed to write scene.json: {e}")

    def should_export_as_glb(self, materials):
        """Check if any material requires GLB export"""
        unreal.log(f"should_export_as_glb called with {len(materials) if materials else 0} materials")
        if not materials:
            unreal.log("No materials provided to should_export_as_glb")
            return False
            
        for i, material in enumerate(materials):
            unreal.log(f"Checking material {i}: {material.get_name() if material else 'None'}")
            if material:
                # Get parent material if this is a material instance
                parent_material = material
                if isinstance(material, unreal.MaterialInstanceConstant):
                    parent_material = material.get_editor_property('parent')

                material_path = parent_material.get_path_name() if parent_material else "None"
                is_in_blendersync = self.is_material_in_blendersync_folder(parent_material)
                
                unreal.log(f"Material check: '{material.get_name()}' at path '{material_path}' - BlenderSync folder: {is_in_blendersync}")

                if not is_in_blendersync:
                    unreal.log(f"GLB export required: Material '{material.get_name()}' is outside BlenderSync folders")
                    return True

        return False

    def assign_materials_to_static_meshes(self, selected_actors):
        """
        Assigns materials from Static Mesh Components to their corresponding Static Mesh assets
        for selected actors in the level.
        """
        for actor in selected_actors:
            if isinstance(actor, unreal.StaticMeshActor):
                static_mesh_component = actor.static_mesh_component
                if not static_mesh_component:
                    unreal.log_warning(f"Actor {actor.get_name()} has no Static Mesh Component, skipping.")
                    continue

                static_mesh = static_mesh_component.static_mesh
                if not static_mesh:
                    unreal.log_warning(f"Actor {actor.get_name()} has no Static Mesh assigned, skipping.")
                    continue

                materials = static_mesh_component.get_materials()

                for index, material in enumerate(materials):
                    if material:
                        current_material = static_mesh.get_material(index)
                        if current_material and current_material.get_path_name() == material.get_path_name():
                            unreal.log(f"Material at index {index} is already assigned for {static_mesh.get_name()}, skipping.")
                            continue
                        static_mesh.set_material(index, material)

                package_name = static_mesh.get_outer().get_path_name()
                try:
                    static_mesh.modify()
                    if unreal.EditorAssetLibrary.save_asset(package_name):
                        unreal.log(f"Saved asset: {package_name} with updated materials.")
                    else:
                        unreal.log_warning(f"Failed to save asset: {package_name}.")
                except Exception as e:
                    unreal.log_error(f"Error saving asset {package_name}: {e}")
            else:
                unreal.log_warning(f"Actor {actor.get_name()} is not a Static Mesh Actor, skipping.")

    def extract_material_parameters(self, material):
        """
        Extract scalar and vector parameters from a material according to specifications:
        1. Metallic: 0 if texture disabled AND scalar disabled, scalar value if texture disabled but scalar enabled
        2. Normal Strength: always save
        3. Roughness: save Roughness Amount if texture disabled
        4. Base Color Tint: save if vector parameter is enabled
        """
        if not material:
            return {}

        params = {}

        try:
            if isinstance(material, unreal.MaterialInstanceConstant):
                # Get scalar parameters
                scalar_params = material.get_editor_property('scalar_parameter_values') or []
                # Get texture parameters
                texture_params = material.get_editor_property('texture_parameter_values') or []
                # Get vector parameters
                vector_params = material.get_editor_property('vector_parameter_values') or []

                # Build lookup dictionaries
                scalar_dict = {}
                for param in scalar_params:
                    param_info = param.get_editor_property('parameter_info')
                    param_name = str(param_info.name).lower()
                    param_value = param.get_editor_property('parameter_value')
                    scalar_dict[param_name] = param_value

                texture_dict = {}
                for param in texture_params:
                    param_info = param.get_editor_property('parameter_info')
                    param_name = str(param_info.name).lower()
                    param_value = param.get_editor_property('parameter_value')
                    texture_dict[param_name] = param_value

                vector_dict = {}
                for param in vector_params:
                    param_info = param.get_editor_property('parameter_info')
                    param_name = str(param_info.name).lower()
                    param_value = param.get_editor_property('parameter_value')
                    vector_dict[param_name] = param_value

                # 1. Metallic parameter
                has_metallic_texture = texture_dict.get('metallic') is not None
                metallic_amount = scalar_dict.get('metallic amount', scalar_dict.get('metallicamount'))

                if not has_metallic_texture:
                    if metallic_amount is not None:
                        params['metallic'] = float(metallic_amount)
                    else:
                        params['metallic'] = 0.0

                # 2. Normal Strength (always save)
                normal_strength = scalar_dict.get('normal strength', scalar_dict.get('normalstrength'))
                if normal_strength is not None:
                    params['normal_strength'] = float(normal_strength)

                # 3. Roughness
                has_roughness_texture = texture_dict.get('roughness') is not None
                roughness_amount = scalar_dict.get('roughness amount', scalar_dict.get('roughnessamount'))

                if not has_roughness_texture and roughness_amount is not None:
                    params['roughness'] = float(roughness_amount)

                # 4. Base Color Tint
                base_color_tint = vector_dict.get('base color tint', vector_dict.get('basecolortint'))
                if base_color_tint is not None:
                    # Convert LinearColor to list [R, G, B, A]
                    params['base_color_tint'] = [
                        float(base_color_tint.r),
                        float(base_color_tint.g),
                        float(base_color_tint.b),
                        float(base_color_tint.a)
                    ]

                if params:
                    unreal.log(f"Extracted parameters for material '{material.get_name()}': {params}")

        except Exception as e:
            unreal.log_warning(f"Failed to extract parameters from material '{material.get_name()}': {str(e)}")

        return params

    def get_material_textures(self, material):
        """Extract all textures from a material's Param2D slots"""
        texture_info = []

        if not material:
            return texture_info

        texture_params = {
            'basecolor': ['basecolor', 'base color', 'diffuse', 'albedo', '_BC'],
            'metallic': ['metallic', 'metal'],
            'roughness': ['roughness', 'rough'],
            'normal': ['normal', 'norm'],
            'emissive': ['emissive', 'emission'],
            'opacity': ['opacity', 'alpha', 'transparency'],
            'height': ['height', 'displacement', 'disp', 'hgt']
        }

        try:
            if isinstance(material, unreal.MaterialInstanceConstant):
                texture_parameter_data = material.get_editor_property('texture_parameter_values')
                for param_data in texture_parameter_data:
                    param_name = str(param_data.get_editor_property('parameter_info').name).lower()
                    texture = param_data.get_editor_property('parameter_value')

                    if texture:
                        if param_name == "ao_rough_metal":
                            texture_info.append({
                                'texture': texture,
                                'type': 'ao_rough_metal'
                            })
                        else:
                            for tex_type, keywords in texture_params.items():
                                if any(keyword in param_name for keyword in keywords):
                                    texture_info.append({
                                        'texture': texture,
                                        'type': tex_type
                                    })
                                    break
            else:
                texture_parameter_infos = unreal.MaterialEditingLibrary.get_texture_parameter_names(material)
                for param_info in texture_parameter_infos:
                    param_name = str(param_info).lower()
                    texture = unreal.MaterialEditingLibrary.get_material_default_texture_parameter_value(
                        material,
                        param_info
                    )

                    if texture:
                        if param_name == "ao_rough_metal":
                            texture_info.append({
                                'texture': texture,
                                'type': 'ao_rough_metal'
                            })
                        else:
                            for tex_type, keywords in texture_params.items():
                                if any(keyword in param_name for keyword in keywords):
                                    texture_info.append({
                                        'texture': texture,
                                        'type': tex_type
                                    })
                                    break

        except Exception as e:
            unreal.log_warning(f"Error getting textures from material {material.get_name()}: {str(e)}")

        return texture_info

    def export_texture(self, texture, material_name, texture_type):
        """Export a single texture with proper naming convention"""
        if not texture:
            return None

        if texture_type == 'ao_rough_metal':
            try:
                roughness_filename = f"T_{material_name}_roughness.png"
                roughness_path = os.path.join(self.export_directory, roughness_filename)

                export_task = unreal.AssetExportTask()
                export_task.set_editor_property('automated', True)
                export_task.set_editor_property('filename', roughness_path)
                export_task.set_editor_property('replace_identical', True)
                export_task.set_editor_property('prompt', False)
                export_task.set_editor_property('object', texture)

                unreal.Exporter.run_asset_export_task(export_task)
                unreal.log(f"Exported roughness texture: {roughness_filename}")

                metallic_filename = f"T_{material_name}_metallic.png"
                metallic_path = os.path.join(self.export_directory, metallic_filename)

                export_task.set_editor_property('filename', metallic_path)
                unreal.Exporter.run_asset_export_task(export_task)
                unreal.log(f"Exported metallic texture: {metallic_filename}")

                return [roughness_path, metallic_path]
            except Exception as e:
                unreal.log_error(f"Failed to export AO_Rough_Metal textures for {material_name}: {str(e)}")
                return None
        else:
            texture_filename = f"T_{material_name}_{texture_type}.png"
            texture_path = os.path.join(self.export_directory, texture_filename)

            try:
                export_task = unreal.AssetExportTask()
                export_task.set_editor_property('automated', True)
                export_task.set_editor_property('filename', texture_path)
                export_task.set_editor_property('replace_identical', True)
                export_task.set_editor_property('prompt', False)
                export_task.set_editor_property('object', texture)

                unreal.Exporter.run_asset_export_task(export_task)
                unreal.log(f"Exported texture: {texture_filename}")
                return texture_path
            except Exception as e:
                unreal.log_error(f"Failed to export texture {texture_filename}: {str(e)}")
                return None

    def export_actor_with_transforms(self, actor, export_format="fbx"):
        """Export actor with preserved transforms using a temporary level setup.

        Also enforces that the exported FBX/GLB filename and the exported node/mesh name
        match the Static Mesh asset name (or actor label as a fallback).
        """
        if not isinstance(actor, unreal.StaticMeshActor):
            return False

        try:
            export_name = self._get_export_name(actor)
            static_mesh_component = actor.static_mesh_component
            if not static_mesh_component:
                return False

            world_transform = static_mesh_component.get_world_transform()
            location = world_transform.translation
            rotation = world_transform.rotation.rotator()
            scale = world_transform.scale3d

            unreal.log(
                f"Actor '{actor.get_name()}' export as '{export_name}' - Location: {location}, Rotation: {rotation}, Scale: {scale}"
            )

            # Store original transform and label so we can restore after export
            original_transform = actor.get_actor_transform()
            try:
                original_label = actor.get_actor_label()
            except Exception:
                original_label = None

            try:
                # Temporarily set actor label to export_name so the exported node uses this name
                try:
                    if original_label != export_name:
                        actor.set_actor_label(export_name, True)
                except Exception:
                    pass

                # Temporarily move actor to world origin with its component transform applied
                # This ensures the exported mesh has the correct relative positioning
                # Note: FBX exporter will convert from cm to meters automatically
                actor.set_actor_transform(world_transform, False, True)

                # Select only this actor for export
                self.editor_actor_subsystem.clear_actor_selection_set()
                self.editor_actor_subsystem.set_actor_selection_state(actor, True)

                # Export the actor with its transforms
                if export_format.lower() == "glb":
                    success = self.export_actor_as_glb(actor, export_name)
                else:
                    success = self.export_actor_as_fbx(actor, export_name)

                return success

            finally:
                # Always restore original transform and label
                actor.set_actor_transform(original_transform, False, True)
                try:
                    if original_label is not None and actor.get_actor_label() != original_label:
                        actor.set_actor_label(original_label, True)
                except Exception:
                    pass

        except Exception as e:
            unreal.log_error(f"Failed to export actor with transforms {actor.get_name()}: {str(e)}")
            return False

    def export_actor_as_glb(self, actor, actor_name):
        """Export selected actor as GLB using level export"""
        glb_path = os.path.join(self.export_directory, f"{actor_name}.glb")
        
        try:
            # Use level export to capture actor transforms
            export_task = unreal.AssetExportTask()
            export_task.set_editor_property('automated', True)
            export_task.set_editor_property('filename', glb_path)
            export_task.set_editor_property('replace_identical', True)
            export_task.set_editor_property('prompt', False)
            export_task.set_editor_property('selected', True)  # Export only selected actors
            
            # Get the current world for export
            world = self.editor_subsystem.get_editor_world()
            export_task.set_editor_property('object', world)
            
            # Execute the export
            unreal.Exporter.run_asset_export_task(export_task)
            unreal.log(f"Exported actor as GLB with transforms: {actor_name}.glb")
            return True
            
        except Exception as e:
            unreal.log_error(f"Failed to export actor as GLB {actor_name}: {str(e)}")
            return False

    def export_actor_as_fbx(self, actor, actor_name):
        """Export selected actor as FBX using level export"""
        fbx_path = os.path.join(self.export_directory, f"{actor_name}.fbx")
        
        try:
            # Use level export to capture actor transforms
            export_task = unreal.AssetExportTask()
            export_task.set_editor_property('automated', True)
            export_task.set_editor_property('filename', fbx_path)
            export_task.set_editor_property('replace_identical', True)
            export_task.set_editor_property('prompt', False)
            export_task.set_editor_property('selected', True)  # Export only selected actors
            
            # Configure FBX export options for better transform preservation
            export_options = unreal.FbxExportOption()
            export_options.collision = False
            export_options.map_skeletal_motion_to_root = False
            export_options.export_morph_targets = False
            export_options.level_of_detail = False  # force a single LOD export
            if hasattr(export_options, "static_mesh_export_lod"):
                export_options.static_mesh_export_lod = 0  # always export the highest LOD
            else:
                try:
                    export_options.set_editor_property("static_mesh_export_lod", 0)
                except Exception:
                    unreal.log_warning("BlenderSync: static_mesh_export_lod option not available; defaulting to engine export settings.")
            # Ensure materials are included if the option exists
            try:
                export_options.set_editor_property('export_materials', True)
            except Exception:
                pass

            export_task.set_editor_property('options', export_options)
            
            # Get the current world for export
            world = self.editor_subsystem.get_editor_world()
            export_task.set_editor_property('object', world)
            
            # Execute the export
            unreal.Exporter.run_asset_export_task(export_task)
            unreal.log(f"Exported actor as FBX with transforms: {actor_name}.fbx")
            return True
            
        except Exception as e:
            unreal.log_error(f"Failed to export actor as FBX {actor_name}: {str(e)}")
            return False

    def export_glb(self, asset, asset_name):
        """Export asset as GLB (legacy method - now used for assets only)"""
        glb_path = os.path.join(self.export_directory, f"{asset_name}.glb")

        try:
            export_task = unreal.AssetExportTask()
            export_task.set_editor_property('automated', True)
            export_task.set_editor_property('filename', glb_path)
            export_task.set_editor_property('replace_identical', True)
            export_task.set_editor_property('prompt', False)
            export_task.set_editor_property('object', asset)

            unreal.Exporter.run_asset_export_task(export_task)
            unreal.log(f"Exported asset as GLB: {asset_name}.glb")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to export GLB for {asset_name}: {str(e)}")
            return False

    def export_fbx(self, asset, asset_name):
        """Export asset as FBX (legacy method - now used for assets only)"""
        fbx_path = os.path.join(self.export_directory, f"{asset_name}.fbx")

        try:
            export_task = unreal.AssetExportTask()
            export_task.set_editor_property('automated', True)
            export_task.set_editor_property('filename', fbx_path)
            export_task.set_editor_property('replace_identical', True)
            export_task.set_editor_property('prompt', False)
            export_task.set_editor_property('object', asset)

            export_options = unreal.FbxExportOption()
            export_options.collision = False
            export_options.level_of_detail = False
            if hasattr(export_options, "static_mesh_export_lod"):
                export_options.static_mesh_export_lod = 0
            else:
                try:
                    export_options.set_editor_property("static_mesh_export_lod", 0)
                except Exception:
                    unreal.log_warning("BlenderSync: static_mesh_export_lod option not available; defaulting to engine export settings.")
            try:
                export_options.set_editor_property('export_materials', True)
            except Exception:
                pass
            export_task.set_editor_property('options', export_options)

            unreal.Exporter.run_asset_export_task(export_task)
            unreal.log(f"Exported asset: {asset_name}.fbx")
            return True
        except Exception as e:
            unreal.log_error(f"Failed to export FBX for {asset_name}: {str(e)}")
            return False

    def export_actor(self, actor):
        """Export an actor and its materials with preserved transforms"""
        if isinstance(actor, unreal.StaticMeshActor):
            static_mesh_component = actor.get_editor_property('static_mesh_component')
            if static_mesh_component:
                static_mesh = static_mesh_component.get_editor_property('static_mesh')
                if static_mesh:
                    # Skip if this is a collision mesh component
                    if 'UCX_' in static_mesh.get_name() or 'UBX_' in static_mesh.get_name():
                        unreal.log(f"Skipping collision mesh: {static_mesh.get_name()}")
                        return

                    # Build an effective materials list per slot, respecting overrides
                    num_sections = static_mesh.get_num_sections(0)  # 0 is the LOD index

                    # Prefer resolved component materials (includes base where no override)
                    component_materials = static_mesh_component.get_materials() or []

                    # Fallback/merge in case component_materials length doesn't cover all slots
                    override_materials = static_mesh_component.get_editor_property('override_materials') or []

                    materials = []
                    for i in range(num_sections):
                        # Try resolved component material first
                        mat = component_materials[i] if i < len(component_materials) else None
                        if not mat:
                            # Then try explicit override
                            mat = override_materials[i] if i < len(override_materials) else None
                        if not mat:
                            # Finally fall back to static mesh asset material
                            mat = static_mesh.get_material(i)
                        materials.append(mat)

                    comp_count = len([m for m in component_materials if m is not None])
                    unreal.log(f"Using {comp_count} component materials (resolved) for {static_mesh.get_name()}")

                    # Ensure the component has explicit overrides for all slots before export
                    try:
                        for i, mat in enumerate(materials):
                            if mat is not None:
                                current = static_mesh_component.get_material(i)
                                if current is None or current.get_path_name() != mat.get_path_name():
                                    static_mesh_component.set_material(i, mat)
                        unreal.log(f"Applied {len([m for m in materials if m])} materials to component overrides for {static_mesh.get_name()}")
                    except Exception as e:
                        unreal.log_warning(f"Failed to apply component materials for {static_mesh.get_name()}: {str(e)}")

                    unreal.log(f"Final material count: {len([m for m in materials if m])} for {static_mesh.get_name()}")
                    
                    # Debug: Show each material before calling should_export_as_glb
                    for i, mat in enumerate(materials):
                        if mat:
                            unreal.log(f"Material {i}: {mat.get_name()} at {mat.get_path_name()}")
                        else:
                            unreal.log(f"Material {i}: None")

                    # Synchronize Static Mesh asset's static_materials with resolved materials to avoid FBX default slots
                    try:
                        static_slots = list(static_mesh.get_editor_property('static_materials') or [])
                        updated_slots = []
                        for i in range(max(len(static_slots), len(materials), num_sections)):
                            mat = materials[i] if i < len(materials) else None
                            if i < len(static_slots):
                                slot = static_slots[i]
                                new_slot = unreal.StaticMaterial()
                                new_slot.material_slot_name = slot.material_slot_name
                                new_slot.material_interface = mat if mat is not None else slot.material_interface
                                updated_slots.append(new_slot)
                            else:
                                new_slot = unreal.StaticMaterial()
                                # Preserve or synthesize a slot name
                                new_slot.material_slot_name = unreal.Name(f"Slot_{i}")
                                if mat is not None:
                                    new_slot.material_interface = mat
                                updated_slots.append(new_slot)

                        # Force-apply and save so exporter sees slots
                        static_mesh.modify()
                        static_mesh.set_editor_property('static_materials', updated_slots)
                        # Also set per-slot LOD0 mapping explicitly
                        for i in range(min(len(updated_slots), num_sections)):
                            mi = updated_slots[i].material_interface
                            if mi is not None:
                                static_mesh.set_material(i, mi)
                        try:
                            static_mesh.post_edit_change()
                        except Exception:
                            pass
                        pkg_name = static_mesh.get_outer().get_path_name()
                        unreal.EditorAssetLibrary.save_asset(pkg_name)
                        unreal.log(f"Synchronized static materials for {static_mesh.get_name()} (slots: {len(updated_slots)})")
                    except Exception as e:
                        unreal.log_warning(f"Failed to sync static materials for {static_mesh.get_name()}: {str(e)}")

                    unreal.log(f"Checking materials for {static_mesh.get_name()}")
                    if self.should_export_as_glb(materials):
                        unreal.log(f"Exporting as GLB due to materials outside BlenderSync folders")
                        # Export GLB and FBX with preserved transforms
                        self.export_actor_with_transforms(actor, "glb")
                        self.export_actor_with_transforms(actor, "fbx")
                    else:
                        unreal.log(f"All materials are in BlenderSync folders, exporting FBX and textures")
                        # Export FBX with preserved transforms
                        self.export_actor_with_transforms(actor, "fbx")

                        # Export textures for materials
                        for material in materials:
                            if material:
                                material_name = material.get_name()
                                texture_info = self.get_material_textures(material)
                                for info in texture_info:
                                    self.export_texture(info['texture'], material_name, info['type'])

    def run(self):
        """Main execution function"""
        try:
            self.setup_export_path()

            selected_actors = self.editor_actor_subsystem.get_selected_level_actors()

            if not selected_actors:
                unreal.log_warning("No actors selected for export")
                return

            unreal.log("Assigning materials to Static Mesh assets...")
            self.assign_materials_to_static_meshes(selected_actors)

            unreal.log("Starting export process with transform preservation...")
            exported_assets = {}
            manifest_entries = []
            material_params = {}  # Dictionary to store material parameters by material name

            for actor in selected_actors:
                static_mesh = self._get_static_mesh_asset(actor)

                if static_mesh:
                    asset_path = static_mesh.get_path_name()
                    asset_entry = exported_assets.setdefault(asset_path, {"donor": None, "donor_object_name": None})

                    if asset_entry["donor"] is None:
                        asset_entry["donor"] = actor.get_name()
                        asset_entry["donor_object_name"] = self._get_export_name(actor)
                        self.export_actor(actor)

                        # Extract material parameters from this actor's materials
                        if isinstance(actor, unreal.StaticMeshActor):
                            static_mesh_component = actor.static_mesh_component
                            if static_mesh_component:
                                component_materials = static_mesh_component.get_materials() or []
                                for material in component_materials:
                                    if material:
                                        mat_name = material.get_name()
                                        if mat_name not in material_params:
                                            params = self.extract_material_parameters(material)
                                            if params:
                                                material_params[mat_name] = params

                        donor_entry = self._build_instance_entry(
                            actor,
                            asset_entry["donor"],
                            asset_entry["donor_object_name"],
                            static_mesh
                        )
                        if donor_entry:
                            donor_entry["is_donor"] = True
                            manifest_entries.append(donor_entry)
                    else:
                        instance_entry = self._build_instance_entry(
                            actor,
                            asset_entry["donor"],
                            asset_entry.get("donor_object_name"),
                            static_mesh
                        )
                        if instance_entry:
                            unreal.log(f"Recording instance '{instance_entry['name']}' referencing donor '{asset_entry['donor']}'")
                            manifest_entries.append(instance_entry)
                        else:
                            unreal.log_warning(f"Could not record instance data for actor '{actor.get_name()}'")
                else:
                    # Non-static-mesh actors (lights, cameras, etc.) should still be exported normally
                    self.export_actor(actor)

            self._write_scene_manifest(manifest_entries, material_params)

            unreal.log("BlenderSync export completed successfully")

        except Exception as e:
            unreal.log_error(f"Error during BlenderSync export: {str(e)}")

# Create and run the exporter
exporter = BlenderSyncUEExport()
exporter.run()
