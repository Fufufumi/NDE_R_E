import unreal
import os
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
        self.export_directory = os.path.join(project_dir, "BSFromUE5")

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
                    parent_material = material.get_parent()

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
            # Check if the actor is a Static Mesh Actor
            if isinstance(actor, unreal.StaticMeshActor):
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
            else:
                unreal.log_warning(f"Actor {actor.get_name()} is not a Static Mesh Actor, skipping.")

    def get_material_textures(self, material):
        """Extract all textures from a material's Param2D slots"""
        texture_info = []

        if not material:
            return texture_info

        # Define the texture parameters to look for
        texture_params = {
            'basecolor': ['basecolor', 'base color', 'diffuse', 'albedo', '_BC'],
            'metallic': ['metallic', 'metal'],
            'roughness': ['roughness', 'rough'],
            'normal': ['normal', 'norm'],
            'emissive': ['emissive', 'emission'],
            'opacity': ['opacity', 'alpha', 'transparency']
        }

        try:
            # Handle MaterialInstanceConstant differently from base Material
            if isinstance(material, unreal.MaterialInstanceConstant):
                texture_parameter_data = material.get_editor_property('texture_parameter_values')
                for param_data in texture_parameter_data:
                    param_name = str(param_data.get_editor_property('parameter_info').name).lower()
                    texture = param_data.get_editor_property('parameter_value')

                    if texture:
                        # Check for AO_Rough_Metal parameter
                        if param_name == "ao_rough_metal":
                            texture_info.append({
                                'texture': texture,
                                'type': 'ao_rough_metal'
                            })
                        else:
                            # Check which texture type this parameter corresponds to
                            for tex_type, keywords in texture_params.items():
                                if any(keyword in param_name for keyword in keywords):
                                    texture_info.append({
                                        'texture': texture,
                                        'type': tex_type
                                    })
                                    break
            else:
                # Original handling for base Materials
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
                            # Check which texture type this parameter corresponds to
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

        # Handle AO_Rough_Metal texture type specially
        if texture_type == 'ao_rough_metal':
            try:
                # Export roughness texture
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

                # Export metallic texture
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
            # Regular texture export
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

    def create_temporary_actor_for_export(self, original_actor):
        """Create a temporary actor with transforms applied for export"""
        if not isinstance(original_actor, unreal.StaticMeshActor):
            return None
            
        try:
            static_mesh_component = original_actor.static_mesh_component
            if not static_mesh_component or not static_mesh_component.static_mesh:
                return None
                
            # Get the component's world transform
            world_transform = static_mesh_component.get_world_transform()
            
            # Create a new temporary actor at world origin
            temp_actor = self.editor_actor_subsystem.spawn_actor_from_class(
                unreal.StaticMeshActor, 
                unreal.Vector(0, 0, 0), 
                unreal.Rotator(0, 0, 0)
            )
            
            if temp_actor:
                # Set the same static mesh
                temp_actor.static_mesh_component.set_static_mesh(static_mesh_component.static_mesh)
                
                # Copy materials
                materials = static_mesh_component.get_materials()
                for i, material in enumerate(materials):
                    if material:
                        temp_actor.static_mesh_component.set_material(i, material)
                
                # Apply the world transform to position the mesh correctly
                temp_actor.set_actor_transform(world_transform, False, None, True)
                
                # Set a unique name for the temporary actor
                temp_name = f"TempExport_{original_actor.get_name()}"
                temp_actor.set_actor_label(temp_name)
                
                unreal.log(f"Created temporary actor '{temp_name}' with preserved transforms")
                return temp_actor
                
        except Exception as e:
            unreal.log_error(f"Failed to create temporary actor for {original_actor.get_name()}: {str(e)}")
            return None

    def export_actor_with_transforms(self, actor, export_format="fbx"):
        """Export actor with preserved transforms using a temporary level setup"""
        if not isinstance(actor, unreal.StaticMeshActor):
            return False
            
        try:
            # Get actor name for export
            actor_name = actor.get_name()
            
            # Get world transform from the component
            static_mesh_component = actor.static_mesh_component
            if not static_mesh_component:
                return False
                
            world_transform = static_mesh_component.get_world_transform()
            location = world_transform.translation
            rotation = world_transform.rotation.rotator()
            scale = world_transform.scale3d
            
            unreal.log(f"Actor '{actor_name}' transform - Location: {location}, Rotation: {rotation}, Scale: {scale}")
            
            # Store original transform
            original_transform = actor.get_actor_transform()
            
            try:
                # Temporarily move actor to world origin with its component transform applied
                # This ensures the exported mesh has the correct relative positioning
                new_transform = unreal.Transform()
                new_transform.translation = unreal.Vector(0, 0, 0)
                new_transform.rotation = unreal.Quat(0, 0, 0, 1)  # Identity quaternion (no rotation)
                new_transform.scale3d = unreal.Vector(1, 1, 1)
                
                # Apply the component's world transform as the actor transform
                actor.set_actor_transform(world_transform, False, True)
                
                # Select only this actor for export
                self.editor_actor_subsystem.clear_actor_selection_set()
                self.editor_actor_subsystem.set_actor_selection_state(actor, True)
                
                # Export the actor with its transforms
                if export_format.lower() == "glb":
                    success = self.export_actor_as_glb(actor, actor_name)
                else:
                    success = self.export_actor_as_fbx(actor, actor_name)
                    
                return success
                
            finally:
                # Always restore original transform
                actor.set_actor_transform(original_transform, False, True)
                
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
            # Create export task
            export_task = unreal.AssetExportTask()
            export_task.set_editor_property('automated', True)
            export_task.set_editor_property('filename', glb_path)
            export_task.set_editor_property('replace_identical', True)
            export_task.set_editor_property('prompt', False)
            export_task.set_editor_property('object', asset)

            # Execute the export
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

            # Configure FBX export options
            export_options = unreal.FbxExportOption()
            export_options.collision = False
            export_task.set_editor_property('options', export_options)

            # Execute the export
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

                    # Get materials from both sources and use the best available
                    override_materials = static_mesh_component.get_editor_property('override_materials')
                    
                    # Get materials from static mesh asset
                    num_sections = static_mesh.get_num_sections(0)  # 0 is the LOD index
                    static_mesh_materials = [static_mesh.get_material(i) for i in range(num_sections)]
                    
                    # Count actual materials in each source
                    override_count = len([m for m in (override_materials or []) if m is not None])
                    static_mesh_count = len([m for m in static_mesh_materials if m is not None])
                    
                    # Use override materials if they exist and have actual materials, otherwise use static mesh materials
                    if override_count > 0:
                        unreal.log(f"Using {override_count} override materials for {static_mesh.get_name()}")
                        materials = override_materials
                    else:
                        unreal.log(f"Using {static_mesh_count} static mesh materials for {static_mesh.get_name()}")
                        materials = static_mesh_materials

                    unreal.log(f"Final material count: {len([m for m in materials if m])} for {static_mesh.get_name()}")
                    
                    # Debug: Show each material before calling should_export_as_glb
                    for i, mat in enumerate(materials):
                        if mat:
                            unreal.log(f"Material {i}: {mat.get_name()} at {mat.get_path_name()}")
                        else:
                            unreal.log(f"Material {i}: None")

                    if self.should_export_as_glb(materials):
                        # Path 1: Material outside BlenderSync folders
                        unreal.log(f"Material outside BlenderSync folders detected for {static_mesh.get_name()}")
                        # Export GLB and FBX with preserved transforms
                        self.export_actor_with_transforms(actor, "glb")
                        self.export_actor_with_transforms(actor, "fbx")
                    else:
                        # Path 2: All materials in BlenderSync folders
                        # Export FBX with preserved transforms
                        self.export_actor_with_transforms(actor, "fbx")
                        # Export all textures separately
                        for material in materials:
                            if material:
                                material_name = material.get_name()
                                texture_info = self.get_material_textures(material)
                                for info in texture_info:
                                    self.export_texture(info['texture'], material_name, info['type'])

    def export_asset(self, asset):
        """Export an asset and its materials (for non-actor exports)"""
        if not asset:
            return

        asset_name = asset.get_name()

        # Get materials based on asset type
        if isinstance(asset, unreal.StaticMesh):
            num_sections = asset.get_num_sections(0)
            materials = [asset.get_material(i) for i in range(num_sections) if asset.get_material(i)]
        elif isinstance(asset, unreal.SkeletalMesh):
            materials = asset.get_materials()
        else:
            materials = []

        if self.should_export_as_glb(materials):
            # Path 1: Material outside BlenderSync folders
            unreal.log(f"Material outside BlenderSync folders detected for {asset_name}")
            # Export GLB with embedded materials
            self.export_glb(asset, asset_name)
            # Export FBX without textures
            self.export_fbx(asset, asset_name)
        else:
            # Path 2: All materials in BlenderSync folders
            # Export FBX
            self.export_fbx(asset, asset_name)
            # Export all textures separately
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

            # Get selected actors
            selected_actors = self.editor_actor_subsystem.get_selected_level_actors()

            if not selected_actors:
                unreal.log_warning("No actors selected for export")
                return

            # First, assign materials to static meshes
            unreal.log("Assigning materials to Static Mesh assets...")
            self.assign_materials_to_static_meshes(selected_actors)

            # Then proceed with export with preserved transforms
            unreal.log("Starting export process with transform preservation...")
            for actor in selected_actors:
                self.export_actor(actor)
            unreal.log("BlenderSync export completed successfully")

        except Exception as e:
            unreal.log_error(f"Error during BlenderSync export: {str(e)}")

# Create and run the exporter
exporter = BlenderSyncUEExport()
exporter.run()