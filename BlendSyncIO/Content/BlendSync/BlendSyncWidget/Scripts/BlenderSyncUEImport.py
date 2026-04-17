import unreal
import os
import shutil
import json
from pathlib import Path

class BlenderSyncUEImport:
    def __init__(self):
        self.bs_to_ue5_folder = None
        # Base paths for different asset types
        self.base_path = "/Game/BlendSync"
        self.mesh_path = f"{self.base_path}/Meshes"
        self.material_path = f"{self.base_path}/Materials"
        self.texture_path = f"{self.base_path}/Textures"
        self.master_material_path = f"{self.base_path}/MasterMaterials"

        # Define all master material paths
        self.master_materials = {
            'default': f"{self.master_material_path}/MM_BS_basemat",
            'glass': f"{self.master_material_path}/MM_BS_basemat_glass",
            'fabric': f"{self.master_material_path}/MM_BS_basemat_fabric",
            'foliage': f"{self.master_material_path}/MM_BS_basemat_foliage",
            'displacement': f"{self.master_material_path}/MM_BS_basemat_Disp",
            'decal': f"{self.master_material_path}/MM_BS_Decal"
        }

        # Define foliage keywords for easy maintenance
        self.foliage_keywords = ["foliage", "plant", "flower", "greenery", "vegetation"]
        self.imported_assets = {}

        # NEW: Track processed materials and textures to avoid duplicates
        self.processed_materials = set()
        self.processed_textures = set()
        self.scene_metadata = {}
        self.material_metadata = {}

        # Get subsystems
        self.editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.editor_actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

        # Define a constant for the folder name
        self.IMPORT_FOLDER_NAME = "BlendSyncIO/Unreal"

    def setup_paths(self):
        """Setup and validate required paths"""
        project_dir = unreal.Paths.project_dir()
        self.bs_to_ue5_folder = os.path.join(project_dir, "BlendSyncIO", "Unreal")

        # Create necessary folders in Content directory
        content_dir = os.path.join(project_dir, "Content")
        create_folders = [
            os.path.join(content_dir, "BlendSync", "Meshes"),
            os.path.join(content_dir, "BlendSync", "Materials"),
            os.path.join(content_dir, "BlendSync", "Textures"),
            os.path.join(content_dir, "BlendSync", "MasterMaterials")
        ]

        for folder in create_folders:
            if not os.path.exists(folder):
                os.makedirs(folder)
                unreal.log(f"Created directory: {folder}")

    def load_scene_metadata(self):
        """Load optional transform metadata exported from Blender."""
        self.scene_metadata = {}
        self.material_metadata = {}
        if not self.bs_to_ue5_folder:
            return

        json_path = os.path.join(self.bs_to_ue5_folder, "BS_scene.json")
        if not os.path.exists(json_path):
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
            objects = payload.get("objects", [])
            self.scene_metadata = {
                entry.get("name"): entry
                for entry in objects
                if entry.get("name")
            }
            self.material_metadata = payload.get("materials", {})
            if self.scene_metadata:
                unreal.log(f"Loaded stored transforms for {len(self.scene_metadata)} object(s)")
        except Exception as exc:
            unreal.log_warning(f"Failed to load BS_scene.json: {str(exc)}")
            self.scene_metadata = {}
            self.material_metadata = {}

    def run(self):
        """Main execution function"""
        try:
            self.setup_paths()
            self.load_scene_metadata()
            fbx_files = self.get_fbx_files()

            if not fbx_files:
                self._show_error("Import Error", f"No FBX files found in the {self.IMPORT_FOLDER_NAME} folder")
                return

            # Process each FBX - without cleaning the folder inside the loop
            for fbx_file in fbx_files:
                unreal.log(f"Processing {fbx_file}...")
                success = self.process_single_fbx(fbx_file)
                if not success:
                    unreal.log_warning(f"Failed to process {fbx_file}, continuing with next file")

            # Finally, clean up import folder once
            self.cleanup_import_folder()
            unreal.log("BlenderSync import completed successfully")

        except Exception as e:
            unreal.log_error(f"Error during BlenderSync import: {str(e)}")
            self._show_error("Import Error", str(e))

    def get_fbx_files(self):
        """Get list of FBX files in BSToUE5 folder"""
        if not os.path.exists(self.bs_to_ue5_folder):
            return []
        return [f for f in os.listdir(self.bs_to_ue5_folder) if f.lower().endswith('.fbx')]

    def _show_error(self, title, message):
        """Display an error dialog in Unreal (fallback to logging)."""
        try:
            unreal.EditorDialog.show_message(title, message, unreal.AppMsgType.OK)
        except Exception:
            unreal.log_error(f"{title}: {message}")

    # Enhanced approach for setting the metallic parameter
    def process_textures_for_material(self, material_name, material_instance):
        """Process and assign textures for a material"""
        if not material_instance:
            return

        texture_mapping = {
            'basecolor': 'Base Color',
            'metallic': 'Metallic',
            'roughness': 'Roughness',
            'normal': 'Normal',
            'opacity': 'Opacity',
            'emissive': 'Emissive',
            'height': 'Height'
        }

        textures = self.get_related_textures(material_name)
        has_roughness_texture = any('roughness' in t.lower() for t in textures)
        has_metallic_texture = any(
            ('metallic' in t.lower()) or ('metal' in t.lower())
            for t in textures
        )
        metadata_candidates = [material_name]
        if not material_name.startswith("MI_"):
            metadata_candidates.append(f"MI_{material_name}")
        else:
            metadata_candidates.append(material_name[3:])

        material_metadata = {}
        for key in metadata_candidates:
            if key in self.material_metadata:
                material_metadata = self.material_metadata[key]
                break

        # Check for special textures
        has_emissive = any('emissive' in t.lower() for t in textures)
        has_opacity  = any('opacity'  in t.lower() for t in textures)
        has_height   = any('height'   in t.lower() for t in textures)

        try:
            target_metallic_texture_amount = 1.0 if has_metallic_texture else 0.0
            unreal.log(
                f"Setting Metallic Texture Amount to {target_metallic_texture_amount} for material {material_name}"
            )

            for attempt in range(3):
                unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                    material_instance, 'Metallic Texture Amount', target_metallic_texture_amount
                )
                unreal.EditorAssetLibrary.save_loaded_asset(material_instance)
                current_value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(
                    material_instance, 'Metallic Texture Amount'
                )
                unreal.log(f"Attempt {attempt+1}: Metallic Texture Amount value: {current_value}")

            # NEW: Configure UV channel parameters for proper UV mapping
            self.configure_uv_channels(material_instance, material_name)

            # Emissive
            if has_emissive:
                unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                    material_instance, 'Use Emissive?', True
                )
                unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                    material_instance, 'Use emissive', 1.0
                )
                # Set Emissive Brightness to 2.0 when emissive texture is detected
                unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                    material_instance, 'Emissive Brightness', 2.0
                )
                unreal.log(f"Set Emissive Brightness to 2.0 for material {material_name}")

            # Opacity
            if has_opacity:
                unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                    material_instance, 'Use Opacity Mask?', True
                )

            # Height/Displacement
            if has_height:
                unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                    material_instance, 'Use Displacement?', True
                )

            # Import and assign each texture
            for texture_file in textures:
                # Skip AO if you don't need it
                if 'ao' in texture_file.lower():
                    continue

                # NEW: Skip already processed textures
                if texture_file in self.processed_textures:
                    unreal.log(f"Skipping already processed texture: {texture_file}")
                    texture_path = f"{self.texture_path}/{os.path.splitext(texture_file)[0]}"
                    texture_obj = unreal.load_object(None, texture_path)
                else:
                    texture_path = self.import_texture(texture_file)
                    if texture_path:
                        texture_obj = self.convert_to_virtual_texture(texture_path)
                        # NEW: Mark texture as processed and remove the file
                        self.processed_textures.add(texture_file)
                        self.remove_texture_file(texture_file)

                if texture_obj:
                    # Match the right parameter
                    lower_tex = texture_file.lower()
                    for suffix, param_name in texture_mapping.items():
                        if suffix in lower_tex:
                            unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
                                material_instance, param_name, texture_obj
                            )
                            break

            if material_metadata:
                self._apply_base_color_override(material_name, material_instance, material_metadata)
                self._apply_metallic_override(
                    material_name,
                    material_instance,
                    material_metadata,
                    has_metallic_texture
                )
                if not has_roughness_texture:
                    self._apply_roughness_override(material_name, material_instance, material_metadata)
                self._apply_normal_strength_override(material_name, material_instance, material_metadata)
                self._apply_emissive_overrides(
                    material_name,
                    material_instance,
                    material_metadata,
                    has_emissive
                )
                self._apply_mapping_override(material_name, material_instance, material_metadata)

            # Final save to ensure all changes are persisted
            unreal.EditorAssetLibrary.save_loaded_asset(material_instance)

            # Final verification
            final_value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(
                material_instance, 'Metallic Texture Amount'
            )
            unreal.log(f"Final Metallic Texture Amount value: {final_value}")

        except Exception as e:
            unreal.log_error(f"Error processing textures for material {material_name}: {str(e)}")

    def _apply_roughness_override(self, material_name, material_instance, metadata):
        roughness_value = metadata.get("roughness")
        if roughness_value is None:
            return

        try:
            self._set_scalar_parameter_with_fallback(
                material_instance,
                ['Roughness Texture Amount', 'RoughnessTextureAmount'],
                0.0
            )
            applied = self._set_scalar_parameter_with_fallback(
                material_instance,
                ['Roughness Amount', 'RoughnessAmount'],
                float(roughness_value)
            )
            if applied:
                unreal.log(f"Applied roughness override ({roughness_value}) to material {material_name}")
            else:
                unreal.log_warning(f"Failed to apply roughness override for {material_name}: parameter missing")
        except Exception as exc:
            unreal.log_warning(f"Failed to apply roughness override for {material_name}: {str(exc)}")

    def _apply_normal_strength_override(self, material_name, material_instance, metadata):
        normal_strength = metadata.get("normal_strength")
        if normal_strength is None:
            return

        try:
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                material_instance, 'Normal Strength', float(normal_strength)
            )
            unreal.log(f"Applied normal strength {normal_strength} to material {material_name}")
        except Exception as exc:
            unreal.log_warning(f"Failed to set Normal Strength for {material_name}: {str(exc)}")

    def _apply_base_color_override(self, material_name, material_instance, metadata):
        base_color = metadata.get("base_color")
        if not base_color:
            return

        if not isinstance(base_color, (list, tuple)) or len(base_color) < 3:
            return

        color = unreal.LinearColor(
            float(base_color[0]),
            float(base_color[1]),
            float(base_color[2]),
            1.0
        )
        vector_applied = self._set_vector_parameter_with_fallback(
            material_instance,
            ['Base Color Tint', 'BaseColorTint'],
            color
        )
        if not vector_applied:
            unreal.log_warning(f"Failed to apply base color override for {material_name}: parameter missing")
            return

        self._set_static_switch_with_fallback(
            material_instance,
            ['Use Base Color Tint', 'Use Base Color Tint?', 'Use base color tint', 'Use base color tint?'],
            True
        )
        self._set_scalar_parameter_with_fallback(
            material_instance,
            ['Use base color tint', 'Use base color tint?'],
            1.0
        )
        unreal.log(f"Applied base color tint override to material {material_name}")

    def _apply_metallic_override(self, material_name, material_instance, metadata, has_metallic_texture):
        metallic_value = metadata.get("metallic")
        if metallic_value is None or has_metallic_texture:
            return

        self._set_scalar_parameter_with_fallback(
            material_instance,
            ['Metallic Texture Amount', 'MetallicTextureAmount'],
            0.0
        )
        applied = self._set_scalar_parameter_with_fallback(
            material_instance,
            ['Metallic Amount', 'MetallicAmount'],
            float(metallic_value)
        )
        if applied:
            unreal.log(f"Applied metallic override ({metallic_value}) to material {material_name}")
        else:
            unreal.log_warning(f"Failed to apply metallic override for {material_name}: parameter missing")

    def _apply_emissive_overrides(self, material_name, material_instance, metadata, has_emissive_texture):
        emission_color = metadata.get("emission_color")
        emission_strength = metadata.get("emission_strength")
        if not emission_color and emission_strength is None:
            return

        has_color = isinstance(emission_color, (list, tuple)) and len(emission_color) >= 3
        if not has_color and emission_strength is None:
            return

        if has_emissive_texture:
            self._set_static_switch_with_fallback(
                material_instance,
                ['Use Emissive?', 'Use Emissive', 'Use emissive?'],
                True
            )
            self._set_scalar_parameter_with_fallback(
                material_instance,
                ['Use emissive', 'Use Emissive'],
                1.0
            )

        if has_color:
            emissive_color = unreal.LinearColor(
                float(emission_color[0]),
                float(emission_color[1]),
                float(emission_color[2]),
                1.0
            )
            self._set_vector_parameter_with_fallback(
                material_instance,
                ['Emissive Color Overlay', 'EmissiveColorOverlay'],
                emissive_color
            )

        if emission_strength is not None:
            self._set_scalar_parameter_with_fallback(
                material_instance,
                ['Emissive Brightness', 'EmissiveBrightness'],
                float(emission_strength)
            )
        unreal.log(f"Applied emissive overrides to material {material_name}")

    def _apply_mapping_override(self, material_name, material_instance, metadata):
        mapping_scale = metadata.get("mapping_scale")
        if not mapping_scale:
            return

        if not isinstance(mapping_scale, (list, tuple)) or len(mapping_scale) < 2:
            return

        scale_vector = unreal.LinearColor(
            float(mapping_scale[0]),
            float(mapping_scale[1]),
            0.0,
            0.0
        )
        applied = self._set_vector_parameter_with_fallback(
            material_instance,
            ['UV Texture Scale XY', 'UVTextureScaleXY'],
            scale_vector
        )
        if applied:
            unreal.log(f"Applied UV Texture Scale XY override to material {material_name}")
        else:
            unreal.log_warning(f"Failed to apply mapping override for {material_name}: parameter missing")

    def _set_scalar_parameter_with_fallback(self, material_instance, names, value):
        for name in names:
            try:
                unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                    material_instance, name, value
                )
                return name
            except Exception:
                continue
        return None

    def _set_vector_parameter_with_fallback(self, material_instance, names, value):
        for name in names:
            try:
                unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
                    material_instance, name, value
                )
                return name
            except Exception:
                continue
        return None

    def _set_static_switch_with_fallback(self, material_instance, names, value):
        for name in names:
            try:
                unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                    material_instance, name, value
                )
                return name
            except Exception:
                continue
        return None

    # NEW: Helper function to configure UV channels
    def configure_uv_channels(self, material_instance, material_name):
        """Configure UV channel parameters for proper UV mapping"""
        try:
            # Get the associated mesh to check its UV channel count
            mesh_uv_channels = self.get_mesh_uv_channel_count(material_name)
            
            # Determine which UV channel to use based on mesh properties and material name
            target_uv_channel = self.determine_optimal_uv_channel(material_name, mesh_uv_channels)
            
            # Comprehensive list of UV channel parameter names that might exist in master materials
            uv_parameters = [
                'UV Channel',
                'UV Index',
                'Texture Coordinate Index',
                'UV Set',
                'TexCoord',
                'Base Color UV Channel',
                'Normal UV Channel',
                'Metallic UV Channel',
                'Roughness UV Channel',
                'UV Coordinate',
                'Texture Coordinates',
                'UVMap',
                'UVIndex',
                'UV_Channel',
                'UV_Index',
                'TextureCoordinateIndex',
                'MainUVChannel',
                'PrimaryUVChannel',
                'UV0Channel',
                'UV1Channel',
                'UVMapIndex',
                'CoordinateIndex',
                'BaseColorUVChannel',
                'NormalUVChannel',
                'MetallicUVChannel',
                'RoughnessUVChannel',
                'EmissiveUVChannel',
                'OpacityUVChannel',
                'HeightUVChannel'
            ]
            
            # Get all scalar parameters to check which UV parameters exist
            parameters_set = 0
            scalar_name_getter = getattr(
                unreal.MaterialEditingLibrary,
                'get_material_instance_scalar_parameter_names',
                None
            )
            if callable(scalar_name_getter):
                try:
                    scalar_params = scalar_name_getter(material_instance)
                    
                    for param_name in scalar_params:
                        param_str = str(param_name)
                        if any(uv_param.lower() in param_str.lower() for uv_param in uv_parameters):
                            current_value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(
                                material_instance, param_name
                            )
                            unreal.log(f"Found UV parameter '{param_str}' with current value: {current_value}")
                            
                            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                                material_instance, param_name, float(target_uv_channel)
                            )
                            unreal.log(f"Set UV parameter '{param_str}' to {target_uv_channel}")
                            parameters_set += 1
                except Exception as e:
                    unreal.log_warning(f"Could not access scalar parameters for UV configuration: {str(e)}")
            
            # NEW: Also check vector parameters that might control UV coordinates
            vector_name_getter = getattr(
                unreal.MaterialEditingLibrary,
                'get_material_instance_vector_parameter_names',
                None
            )
            if callable(vector_name_getter):
                try:
                    vector_params = vector_name_getter(material_instance)
                    
                    for param_name in vector_params:
                        param_str = str(param_name)
                        if any(uv_keyword in param_str.lower() for uv_keyword in ['uv', 'coord', 'mapping']):
                            current_value = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(
                                material_instance, param_name
                            )
                            unreal.log(f"Found UV vector parameter '{param_str}' with current value: {current_value}")
                except Exception as e:
                    unreal.log_warning(f"Could not access vector parameters for UV configuration: {str(e)}")
            
            # NEW: Also check static switch parameters that might control UV selection
            switch_name_getter = getattr(
                unreal.MaterialEditingLibrary,
                'get_material_instance_static_switch_parameter_names',
                None
            )
            if callable(switch_name_getter):
                try:
                    switch_params = switch_name_getter(material_instance)
                    
                    for param_name in switch_params:
                        param_str = str(param_name)
                        if any(uv_keyword in param_str.lower() for uv_keyword in ['uv', 'coord', 'mapping', 'channel']):
                            current_value = unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(
                                material_instance, param_name
                            )
                            unreal.log(f"Found UV switch parameter '{param_str}' with current value: {current_value}")
                            
                            if target_uv_channel == 0 and 'uv0' in param_str.lower():
                                unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                                    material_instance, param_name, True
                                )
                                unreal.log(f"Enabled UV0 switch parameter '{param_str}'")
                                parameters_set += 1
                            elif target_uv_channel == 1 and 'uv1' in param_str.lower():
                                unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                                    material_instance, param_name, True
                                )
                                unreal.log(f"Enabled UV1 switch parameter '{param_str}'")
                                parameters_set += 1
                except Exception as e:
                    unreal.log_warning(f"Could not access static switch parameters for UV configuration: {str(e)}")
            
            # Also try to set common UV tiling/offset parameters
            try:
                tiling_parameters = [
                    'U Tiling',
                    'V Tiling', 
                    'UV Tiling',
                    'Texture Scale',
                    'U Offset',
                    'V Offset',
                    'UV Offset',
                    'Tiling',
                    'Offset',
                    'Scale'
                ]
                
                for param_name in tiling_parameters:
                    try:
                        # Try to set tiling to 1.0 and offset to 0.0
                        if 'tiling' in param_name.lower() or 'scale' in param_name.lower():
                            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                                material_instance, param_name, 1.0
                            )
                            unreal.log(f"Set tiling parameter '{param_name}' to 1.0")
                            parameters_set += 1
                        elif 'offset' in param_name.lower():
                            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                                material_instance, param_name, 0.0
                            )
                            unreal.log(f"Set offset parameter '{param_name}' to 0.0")
                            parameters_set += 1
                    except:
                        # Parameter doesn't exist, which is fine
                        pass
            except Exception as e:
                unreal.log_warning(f"Could not configure UV tiling/offset parameters: {str(e)}")
            
            # Log summary
            if parameters_set > 0:
                unreal.log(f"Successfully configured {parameters_set} UV-related parameters for material {material_name}")
            else:
                unreal.log_warning(f"No UV parameters found or configured for material {material_name} - this might indicate the master material doesn't expose UV parameters")
                
        except Exception as e:
            unreal.log_error(f"Error configuring UV channels for material {material_name}: {str(e)}")

    # NEW: Helper function to get mesh UV channel count
    def get_mesh_uv_channel_count(self, material_name):
        """Get the UV channel count for the mesh associated with this material"""
        try:
            # Try to find the associated mesh
            for asset_name, asset_path in self.imported_assets.items():
                if material_name in asset_name or asset_name in material_name:
                    asset = unreal.load_object(None, asset_path)
                    if asset and isinstance(asset, unreal.StaticMesh):
                        try:
                            uv_count = asset.get_num_u_vchannels(0)  # LOD 0
                            return uv_count
                        except:
                            pass
            return 1  # Default to 1 UV channel if we can't determine
        except Exception as e:
            unreal.log_warning(f"Could not get UV channel count for material {material_name}: {str(e)}")
            return 1

    # NEW: Helper function to determine optimal UV channel
    def determine_optimal_uv_channel(self, material_name, mesh_uv_channels):
        """Determine the optimal UV channel to use based on material and mesh properties"""
        try:
            # Material-specific UV channel logic
            material_lower = material_name.lower()
            
            # Lightmap materials typically use UV1 (channel 1)
            if 'lightmap' in material_lower or 'lm_' in material_lower:
                if mesh_uv_channels > 1:
                    unreal.log(f"Using UV channel 1 for lightmap material {material_name}")
                    return 1
            
            # Decal materials might use different UV channels
            if 'decal' in material_lower:
                unreal.log(f"Using UV channel 0 for decal material {material_name}")
                return 0
            
            # For GLB/FBX pairs, the GLB might have specific UV layout requirements
            # In many cases, the first UV channel (0) contains the main texture mapping
            # while the second UV channel (1) contains lightmap coordinates
            
            if mesh_uv_channels > 1:
                # If we have multiple UV channels, default to channel 0 for main textures
                # unless it's a specific type that needs a different channel
                unreal.log(f"Multiple UV channels available ({mesh_uv_channels}), using UV channel 0 for {material_name}")
                return 0
            else:
                # Single UV channel, use channel 0
                unreal.log(f"Single UV channel detected, using UV channel 0 for {material_name}")
                return 0
                
        except Exception as e:
            unreal.log_warning(f"Error determining optimal UV channel for {material_name}: {str(e)}")
            return 0  # Default to UV channel 0

    # NEW: Helper function to remove texture file after processing
    def remove_texture_file(self, texture_file):
        """Remove texture file from import folder after processing"""
        try:
            file_path = os.path.join(self.bs_to_ue5_folder, texture_file)
            if os.path.exists(file_path):
                os.chmod(file_path, 0o777)  # Ensure file is writable
                os.remove(file_path)
                unreal.log(f"Removed processed texture file: {texture_file}")
        except Exception as e:
            unreal.log_warning(f"Failed to remove texture file {texture_file}: {str(e)}")

    def assign_materials_to_mesh(self, asset, material_names):
        """Assign materials to the correct slots in the mesh"""
        try:
            if not isinstance(asset, unreal.StaticMesh):
                return False

            material_slots = asset.get_editor_property('static_materials')
            if not material_slots:
                return False

            updated_slots = []
            for slot in material_slots:
                new_slot = unreal.StaticMaterial()
                new_slot.material_slot_name = slot.material_slot_name

                slot_name = str(slot.material_slot_name)
                base_name = slot_name[3:] if slot_name.startswith('MI_') else slot_name

                material_path = f"{self.material_path}/MI_{base_name}"
                mat_ref = unreal.load_object(None, material_path)

                if mat_ref:
                    new_slot.material_interface = mat_ref
                else:
                    new_slot.material_interface = slot.material_interface

                updated_slots.append(new_slot)

            asset.set_editor_property('static_materials', updated_slots)
            unreal.EditorAssetLibrary.save_loaded_asset(asset)
            return True

        except Exception as e:
            unreal.log_error(f"Error assigning materials to mesh {asset.get_name()}: {str(e)}")
            return False

    def replace_actors_in_scene(self, asset_path):
        """Replace existing actors in scene with newly imported ones"""
        try:
            asset_name = os.path.splitext(os.path.basename(asset_path))[0]
            if '.' in asset_name:
                asset_name = asset_name.split('.')[0]

            # Remove existing actors
            existing_actors = []
            for actor in self.editor_actor_subsystem.get_all_level_actors():
                actor_label = actor.get_actor_label()
                clean_label = actor_label.split('.')[0] if '.' in actor_label else actor_label
                if clean_label == asset_name:
                    existing_actors.append(actor)

            for actor in existing_actors:
                self.editor_actor_subsystem.destroy_actor(actor)

            # Create new actor
            static_mesh = unreal.load_object(None, asset_path)
            if static_mesh and isinstance(static_mesh, unreal.StaticMesh):
                location = unreal.Vector(0, 0, 0)
                rotation = unreal.Rotator(0, 0, 0)
                new_actor = self.editor_actor_subsystem.spawn_actor_from_class(
                    unreal.StaticMeshActor, location, rotation
                )
                if new_actor:
                    new_actor.static_mesh_component.set_static_mesh(static_mesh)
                    new_actor.set_actor_label(asset_name, True)

                    # Ensure clean label
                    current_label = new_actor.get_actor_label()
                    if '.' in current_label:
                        clean_label = current_label.split('.')[0]
                        new_actor.set_actor_label(clean_label, True)

                    self.apply_stored_transform(new_actor, asset_name)

                    # Select the actor
                    self.editor_actor_subsystem.set_actor_selection_state(new_actor, True)
                    unreal.log(f"Created actor with label: {new_actor.get_actor_label()}")
                    return True
            return False

        except Exception as e:
            unreal.log_error(f"Error replacing actors: {str(e)}")
            return False

    def apply_stored_transform(self, actor, asset_name):
        """Apply stored location/rotation/scale from BS_scene.json if available."""
        if not actor or not self.scene_metadata:
            return

        transform_data = self.scene_metadata.get(asset_name)
        if not transform_data:
            return

        try:
            location = transform_data.get("location")
            rotation = transform_data.get("rotation")
            scale = transform_data.get("scale")

            if location and len(location) == 3:
                converted_location = unreal.Vector(location[0], -location[1], location[2])
                actor.set_actor_location(converted_location, False, False)

            if rotation and len(rotation) == 3:
                rotator = unreal.Rotator(rotation[0], rotation[1], rotation[2])
                actor.set_actor_rotation(rotator, False)

            if scale and len(scale) == 3:
                actor.set_actor_scale3d(unreal.Vector(*scale))

            if location or rotation or scale:
                unreal.log(f"Applied stored transform to {asset_name}")
        except Exception as exc:
            unreal.log_warning(f"Failed to apply stored transform for {asset_name}: {str(exc)}")

    def cleanup_import_folder(self):
        """Delete all files and directories in the import folder (called once after all FBXs are done)"""
        try:
            if not os.path.exists(self.bs_to_ue5_folder):
                return

            def force_remove_readonly(func, path, exc_info):
                """Error handler for shutil.rmtree to handle read-only files"""
                import stat
                if func in (os.remove, os.rmdir):
                    if os.path.exists(path):
                        os.chmod(path, stat.S_IWRITE)
                        func(path)

            # First pass: remove files
            for item in os.listdir(self.bs_to_ue5_folder):
                item_path = os.path.join(self.bs_to_ue5_folder, item)
                try:
                    if os.path.isfile(item_path):
                        os.chmod(item_path, 0o777)
                        os.remove(item_path)
                        unreal.log(f"Deleted file: {item}")
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, onerror=force_remove_readonly)
                        unreal.log(f"Deleted directory: {item}")
                except Exception as e:
                    unreal.log_warning(f"Failed to delete {item}: {str(e)}")
                    try:
                        if os.path.exists(item_path):
                            if os.path.isfile(item_path):
                                os.unlink(item_path)
                            else:
                                shutil.rmtree(item_path, ignore_errors=True)
                            unreal.log(f"Deleted {item} on second attempt")
                    except Exception as e2:
                        unreal.log_error(f"Failed to delete {item} after second attempt: {str(e2)}")

            remaining_items = os.listdir(self.bs_to_ue5_folder)
            if remaining_items:
                unreal.log_warning(f"Some items remain in the import folder: {remaining_items}")
            else:
                unreal.log("Import folder cleaned successfully")

        except Exception as e:
            unreal.log_error(f"Error cleaning up import folder: {str(e)}")

    def process_single_fbx(self, fbx_file):
        """Process a single FBX file with its materials and textures, but do NOT delete folder here"""
        try:
            imported_paths = self.import_fbx(fbx_file)
            if not imported_paths:
                return False  # No paths imported means something failed or was empty

            # For each imported asset
            for asset_path in imported_paths:
                asset = unreal.load_object(None, asset_path)
                if not isinstance(asset, unreal.StaticMesh):
                    continue

                # Gather materials
                material_names = self.get_fbx_material_names(asset_path)
                processed_materials_this_run = []

                for material_name in material_names:
                    # NEW: Skip if material has already been processed in a previous run
                    if material_name in self.processed_materials:
                        unreal.log(f"Material {material_name} already processed, skipping creation")
                        processed_materials_this_run.append(material_name)
                        continue

                    if material_name not in processed_materials_this_run:
                        material_instance = self.create_material_instance(material_name)
                        if material_instance:
                            self.process_textures_for_material(material_name, material_instance)
                            processed_materials_this_run.append(material_name)
                            # NEW: Add to global processed materials set
                            self.processed_materials.add(material_name)

                if processed_materials_this_run:
                    self.assign_materials_to_mesh(asset, processed_materials_this_run)

                # Place actor in scene
                self.replace_actors_in_scene(asset_path)

            return True

        except Exception as e:
            unreal.log_error(f"Error processing {fbx_file}: {str(e)}")
            return False

    def get_related_textures(self, material_name):
        """Get textures related to a specific material by name"""
        textures = []
        if not os.path.exists(self.bs_to_ue5_folder):
            return textures

        for file in os.listdir(self.bs_to_ue5_folder):
            if file.startswith(f"T_{material_name}"):
                textures.append(file)
        return textures

    def get_appropriate_material_path(self, material_name):
        """Determine which master material to use based on material name and textures"""
        name_lower = material_name.lower()

        # Check for decal
        if "decal" in name_lower:
            return self.master_materials['decal']

        # Height textures no longer force displacement; still fetch texture list for later use
        textures = self.get_related_textures(material_name)
        if "glass" in name_lower:
            return self.master_materials['glass']
        if "fabric" in name_lower:
            return self.master_materials['fabric']
        if any(keyword in name_lower for keyword in self.foliage_keywords):
            return self.master_materials['foliage']

        return self.master_materials['default']

    def import_fbx(self, fbx_file):
        """Import FBX file into Unreal Engine silently without materials"""
        try:
            asset_name = os.path.splitext(fbx_file)[0]

            fbx_import_options = unreal.FbxImportUI()
            fbx_import_options.set_editor_property('import_mesh', True)
            fbx_import_options.set_editor_property('import_textures', False)
            fbx_import_options.set_editor_property('import_materials', False)
            fbx_import_options.set_editor_property('import_as_skeletal', False)
            fbx_import_options.static_mesh_import_data.set_editor_property('import_translation', unreal.Vector(0.0, 0.0, 0.0))
            fbx_import_options.static_mesh_import_data.set_editor_property('import_rotation', unreal.Rotator(0.0, 0.0, 0.0))
            fbx_import_options.static_mesh_import_data.set_editor_property('import_uniform_scale', 1.0)

            # NEW: Configure UV and material import settings for better compatibility
            try:
                # Ensure UV coordinates are properly imported
                fbx_import_options.static_mesh_import_data.set_editor_property('combine_meshes', False)
                fbx_import_options.static_mesh_import_data.set_editor_property('generate_lightmap_u_vs', True)
                fbx_import_options.static_mesh_import_data.set_editor_property('auto_generate_collision', False)
                
                # NEW: Configure texture coordinate import
                fbx_import_options.texture_import_data.set_editor_property('invert_normal_maps', False)
                
                unreal.log(f"Configured FBX import options for better UV handling")
            except Exception as e:
                unreal.log_warning(f"Could not set advanced FBX import options: {str(e)}")

            import_task = unreal.AssetImportTask()
            import_task.set_editor_property('automated', True)
            # IMPORTANT: Give each FBX a unique Destination Name:
            import_task.set_editor_property('destination_name', asset_name)
            import_task.set_editor_property('destination_path', self.mesh_path)
            import_task.set_editor_property('filename', os.path.join(self.bs_to_ue5_folder, fbx_file))
            import_task.set_editor_property('replace_existing', True)
            import_task.set_editor_property('save', True)
            import_task.set_editor_property('options', fbx_import_options)

            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([import_task])
            imported_paths = import_task.get_editor_property('imported_object_paths')

            if not imported_paths:
                unreal.log_warning(f"No assets were imported for {fbx_file}")
                return []

            # NEW: Log UV information for debugging
            for asset_path in imported_paths:
                self.log_mesh_uv_info(asset_path)

            self.imported_assets[asset_name] = imported_paths[0]
            return imported_paths

        except Exception as e:
            unreal.log_error(f"Error importing FBX '{fbx_file}': {str(e)}")
            return []

    # NEW: Helper function to log UV information for debugging
    def log_mesh_uv_info(self, asset_path):
        """Log UV channel information for imported mesh"""
        try:
            asset = unreal.load_object(None, asset_path)
            if asset and isinstance(asset, unreal.StaticMesh):
                # Get UV channel count
                try:
                    uv_channel_count = asset.get_num_u_vchannels(0)  # LOD 0
                    unreal.log(f"Mesh {asset.get_name()} has {uv_channel_count} UV channels")
                    
                    # Check if we have multiple UV sets
                    if uv_channel_count > 1:
                        unreal.log(f"Multiple UV channels detected - mesh may need UV channel configuration")
                    elif uv_channel_count == 0:
                        unreal.log_warning(f"No UV channels found in mesh {asset.get_name()}")
                except Exception as e:
                    unreal.log_warning(f"Could not get UV channel information for {asset.get_name()}: {str(e)}")
        except Exception as e:
            unreal.log_warning(f"Error logging UV info for {asset_path}: {str(e)}")

    def import_texture(self, texture_file):
        """Import texture into Unreal Engine with naive UDIM support"""
        try:
            base_name = texture_file
            is_udim = False

            # Very naive UDIM check
            if '.100' in texture_file:
                import re
                base_match = re.match(r'(.+?)\.100\d\.(png|jpg|jpeg|tga)$', texture_file, re.IGNORECASE)
                if base_match:
                    base_name = base_match.group(1) + '.' + base_match.group(2)
                    is_udim = True

            import_task = unreal.AssetImportTask()
            import_task.set_editor_property('automated', True)
            import_task.set_editor_property('destination_path', self.texture_path)
            import_task.set_editor_property('filename', os.path.join(self.bs_to_ue5_folder, texture_file))
            import_task.set_editor_property('replace_existing', True)
            import_task.set_editor_property('save', True)

            if is_udim:
                try:
                    import_options = unreal.FbxTextureImportData()
                    import_options.set_editor_property('material_search_location', unreal.MaterialSearchLocation.LOCAL)
                    import_options.set_editor_property('base_material_name', base_name)

                    texture_factory = unreal.TextureFactory()
                    texture_factory.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
                    texture_factory.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
                    texture_factory.set_editor_property('texture_group', unreal.TextureGroup.TEXTUREGROUP_WORLD)

                    import_task.set_editor_property('factory', texture_factory)
                    import_task.set_editor_property('options', import_options)
                    import_task.set_editor_property('group_name', base_name)

                except Exception as e:
                    unreal.log_warning(f"Failed UDIM settings for {texture_file}: {str(e)}")

            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([import_task])
            texture_name = os.path.splitext(base_name)[0]
            return f"{self.texture_path}/{texture_name}"

        except Exception as e:
            unreal.log_error(f"Error importing texture: {str(e)}")
            return None

    def get_fbx_material_names(self, fbx_path):
        """Get material names by combining FBX mesh slots and any texture-derived names."""
        material_names = set()

        # 1) Load the mesh and parse its material slots
        mesh_name = os.path.splitext(os.path.basename(fbx_path))[0]
        asset_path = f"{self.mesh_path}/{mesh_name}"
        asset = unreal.load_object(None, asset_path)
        if asset and isinstance(asset, unreal.StaticMesh):
            material_slots = asset.get_editor_property('static_materials')
            for slot in material_slots:
                slot_name = str(slot.material_slot_name)
                # If a slot is e.g. "MI_ChairLegs", strip off "MI_"
                if slot_name.startswith("MI_"):
                    slot_name = slot_name[3:]
                material_names.add(slot_name)

        # 2) Parse all files in the import folder for anything that starts with 'T_'
        for file in os.listdir(self.bs_to_ue5_folder):
            if file.startswith('T_'):
                parts = file.split('_')
                # e.g. T_Wood_Table_Basecolor.png -> parts=['T','Wood','Table','Basecolor.png']
                if len(parts) >= 3:
                    gleaned = '_'.join(parts[1:-1])
                    material_names.add(gleaned)

        # 3) If we still don't have any material names, default to a single "<MeshName>_Mat"
        if not material_names:
            material_names.add(f"{mesh_name}_Mat")

        result = list(material_names)
        unreal.log(f"Found materials: {result}")
        return result

    def create_material_instance(self, material_name):
        """Create material instance based on master material"""
        try:
            asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
            mat_inst_factory = unreal.MaterialInstanceConstantFactoryNew()

            instance_name = material_name
            if not instance_name.startswith('MI_'):
                instance_name = f"MI_{material_name}"

            existing_instance = self.get_existing_material_instance(instance_name)
            if existing_instance:
                return existing_instance

            material_instance = asset_tools.create_asset(
                instance_name,
                self.material_path,
                unreal.MaterialInstanceConstant,
                mat_inst_factory
            )

            if material_instance:
                parent_path = self.get_appropriate_material_path(material_name)
                parent_mat  = unreal.load_object(None, parent_path)
                if parent_mat:
                    material_instance.set_editor_property('parent', parent_mat)
                    return material_instance
                else:
                    unreal.log_error(f"Failed to load parent material: {parent_path}")

            return None

        except Exception as e:
            unreal.log_error(f"Error creating material instance '{material_name}': {str(e)}")
            return None

    def get_existing_material_instance(self, material_name):
        """Check if a suitable material instance already exists"""
        try:
            if material_name.startswith('MI_'):
                instance_name = material_name
            else:
                instance_name = f"MI_{material_name}"

            instance_path = f"{self.material_path}/{instance_name}"
            material_instance = unreal.load_object(None, instance_path)

            if material_instance and isinstance(material_instance, unreal.MaterialInstanceConstant):
                parent_material = material_instance.get_editor_property('parent')
                if parent_material:
                    parent_path = parent_material.get_path_name()
                    if self.master_material_path in parent_path:
                        unreal.log(f"Found existing valid material instance: {instance_name}")
                        return material_instance

            return None

        except Exception as e:
            unreal.log_error(f"Error checking existing material '{material_name}': {str(e)}")
            return None

    def convert_to_virtual_texture(self, texture_path):
        """Convert imported texture to virtual texture with proper settings"""
        texture = unreal.load_object(None, texture_path)
        if not texture:
            return None

        try:
            tex_lower = texture_path.lower()

            texture.set_editor_property('virtual_texture_streaming', True)
            texture.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_WORLD)
            texture.set_editor_property('filter', unreal.TextureFilter.TF_DEFAULT)

            if 'normal' in tex_lower:
                texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
                texture.set_editor_property('srgb', False)
            elif 'basecolor' in tex_lower:
                texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
                texture.set_editor_property('srgb', True)

                # Attempt to set sRGB
                try:
                    asset_import_data = texture.get_editor_property('asset_import_data')
                    if asset_import_data and hasattr(asset_import_data, 'source_color_settings'):
                        scs = asset_import_data.get_editor_property('source_color_settings')
                        if scs:
                            scs.set_editor_property('encoding_override', unreal.TextureColorEncoding.SRGB)
                            asset_import_data.set_editor_property('source_color_settings', scs)
                            texture.set_editor_property('asset_import_data', asset_import_data)
                except Exception as e:
                    unreal.log_warning(f"Could not set color settings for {texture_path}: {str(e)}")
            else:
                texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
                texture.set_editor_property('srgb', False)

            unreal.EditorAssetLibrary.save_loaded_asset(texture)
            return texture

        except Exception as e:
            unreal.log_warning(f"Failed to convert texture '{texture_path}': {str(e)}")
            return texture

    # NEW: Utility function to fix UV mapping issues in existing materials
    def fix_existing_materials_uv_mapping(self):
        """Fix UV mapping issues for existing BlendSync materials"""
        try:
            unreal.log("Starting UV mapping fix for existing BlendSync materials...")
            
            # Get all material instances in the BlendSync materials folder
            material_assets = unreal.EditorAssetLibrary.list_assets(self.material_path, recursive=True)
            
            fixed_count = 0
            for asset_path in material_assets:
                if asset_path.endswith('.uasset') or asset_path.endswith('.MaterialInstanceConstant'):
                    try:
                        # Load the material instance
                        material_instance = unreal.EditorAssetLibrary.load_asset(asset_path)
                        if material_instance and isinstance(material_instance, unreal.MaterialInstanceConstant):
                            material_name = material_instance.get_name()
                            
                            # Skip if this doesn't look like a BlendSync material
                            if not material_name.startswith('MI_'):
                                continue
                                
                            base_name = material_name[3:] if material_name.startswith('MI_') else material_name
                            
                            unreal.log(f"Fixing UV mapping for material: {material_name}")
                            
                            # Apply UV channel configuration
                            self.configure_uv_channels(material_instance, base_name)
                            
                            # Save the updated material
                            unreal.EditorAssetLibrary.save_loaded_asset(material_instance)
                            fixed_count += 1
                            
                    except Exception as e:
                        unreal.log_warning(f"Failed to fix UV mapping for {asset_path}: {str(e)}")
            
            unreal.log(f"UV mapping fix completed. Fixed {fixed_count} materials.")
            return fixed_count
            
        except Exception as e:
            unreal.log_error(f"Error during UV mapping fix: {str(e)}")
            return 0

    # NEW: Utility function to analyze UV mapping issues
    def analyze_uv_mapping_issues(self):
        """Analyze and report UV mapping issues in BlendSync materials and meshes"""
        try:
            unreal.log("Analyzing UV mapping for BlendSync assets...")
            
            issues_found = []
            
            # Check meshes
            mesh_assets = unreal.EditorAssetLibrary.list_assets(self.mesh_path, recursive=True)
            for asset_path in mesh_assets:
                if asset_path.endswith('.uasset') or asset_path.endswith('.StaticMesh'):
                    try:
                        mesh = unreal.EditorAssetLibrary.load_asset(asset_path)
                        if mesh and isinstance(mesh, unreal.StaticMesh):
                            try:
                                uv_count = mesh.get_num_u_vchannels(0)
                                mesh_name = mesh.get_name()
                                
                                if uv_count == 0:
                                    issues_found.append(f"Mesh '{mesh_name}' has no UV channels")
                                elif uv_count > 1:
                                    unreal.log(f"Mesh '{mesh_name}' has {uv_count} UV channels (normal)")
                                else:
                                    unreal.log(f"Mesh '{mesh_name}' has {uv_count} UV channel")
                                    
                            except Exception as e:
                                issues_found.append(f"Could not get UV info for mesh '{mesh.get_name()}': {str(e)}")
                    except Exception as e:
                        unreal.log_warning(f"Failed to analyze mesh {asset_path}: {str(e)}")
            
            # Check materials
            material_assets = unreal.EditorAssetLibrary.list_assets(self.material_path, recursive=True)
            for asset_path in material_assets:
                if asset_path.endswith('.uasset') or asset_path.endswith('.MaterialInstanceConstant'):
                    try:
                        material = unreal.EditorAssetLibrary.load_asset(asset_path)
                        if material and isinstance(material, unreal.MaterialInstanceConstant):
                            material_name = material.get_name()
                            
                            # Check for UV-related parameters
                            try:
                                scalar_params = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_names(material)
                                uv_params_found = []
                                
                                for param_name in scalar_params:
                                    param_str = str(param_name)
                                    if any(uv_keyword in param_str.lower() for uv_keyword in ['uv', 'coord', 'channel']):
                                        value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, param_name)
                                        uv_params_found.append(f"{param_str}={value}")
                                
                                if uv_params_found:
                                    unreal.log(f"Material '{material_name}' UV parameters: {', '.join(uv_params_found)}")
                                else:
                                    unreal.log(f"Material '{material_name}' has no UV parameters")
                                    
                            except Exception as e:
                                issues_found.append(f"Could not analyze UV parameters for material '{material_name}': {str(e)}")
                                
                    except Exception as e:
                        unreal.log_warning(f"Failed to analyze material {asset_path}: {str(e)}")
            
            if issues_found:
                unreal.log_warning("UV mapping issues found:")
                for issue in issues_found:
                    unreal.log_warning(f"  - {issue}")
            else:
                unreal.log("No major UV mapping issues detected.")
                
            return len(issues_found)
            
        except Exception as e:
            unreal.log_error(f"Error during UV mapping analysis: {str(e)}")
            return -1

    # NEW: Comprehensive parameter discovery function
    def discover_all_material_parameters(self, material_instance_path=None):
        """Discover and log ALL parameters in a material instance for debugging"""
        try:
            if material_instance_path:
                material = unreal.EditorAssetLibrary.load_asset(material_instance_path)
            else:
                # Use the first BlendSync material we can find
                material_assets = unreal.EditorAssetLibrary.list_assets(self.material_path, recursive=True)
                material = None
                for asset_path in material_assets:
                    if asset_path.endswith('.uasset') or asset_path.endswith('.MaterialInstanceConstant'):
                        temp_material = unreal.EditorAssetLibrary.load_asset(asset_path)
                        if temp_material and isinstance(temp_material, unreal.MaterialInstanceConstant):
                            material = temp_material
                            break
            
            if not material:
                unreal.log_error("No material instance found for parameter discovery")
                return
            
            material_name = material.get_name()
            unreal.log(f"=== DISCOVERING ALL PARAMETERS FOR MATERIAL: {material_name} ===")
            
            # Scalar parameters
            try:
                scalar_params = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_names(material)
                unreal.log(f"SCALAR PARAMETERS ({len(scalar_params)}):")
                for param_name in scalar_params:
                    try:
                        value = unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(material, param_name)
                        param_str = str(param_name)
                        is_uv_related = any(uv_keyword in param_str.lower() for uv_keyword in ['uv', 'coord', 'channel', 'map', 'index'])
                        marker = " [UV-RELATED]" if is_uv_related else ""
                        unreal.log(f"  - {param_str} = {value}{marker}")
                    except Exception as e:
                        unreal.log_warning(f"  - {param_name} = ERROR: {str(e)}")
            except Exception as e:
                unreal.log_error(f"Could not get scalar parameters: {str(e)}")
            
            # Vector parameters
            try:
                vector_params = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_names(material)
                unreal.log(f"VECTOR PARAMETERS ({len(vector_params)}):")
                for param_name in vector_params:
                    try:
                        value = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(material, param_name)
                        param_str = str(param_name)
                        is_uv_related = any(uv_keyword in param_str.lower() for uv_keyword in ['uv', 'coord', 'channel', 'map', 'index'])
                        marker = " [UV-RELATED]" if is_uv_related else ""
                        unreal.log(f"  - {param_str} = {value}{marker}")
                    except Exception as e:
                        unreal.log_warning(f"  - {param_name} = ERROR: {str(e)}")
            except Exception as e:
                unreal.log_error(f"Could not get vector parameters: {str(e)}")
            
            # Static switch parameters
            try:
                switch_params = unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_names(material)
                unreal.log(f"STATIC SWITCH PARAMETERS ({len(switch_params)}):")
                for param_name in switch_params:
                    try:
                        value = unreal.MaterialEditingLibrary.get_material_instance_static_switch_parameter_value(material, param_name)
                        param_str = str(param_name)
                        is_uv_related = any(uv_keyword in param_str.lower() for uv_keyword in ['uv', 'coord', 'channel', 'map', 'index'])
                        marker = " [UV-RELATED]" if is_uv_related else ""
                        unreal.log(f"  - {param_str} = {value}{marker}")
                    except Exception as e:
                        unreal.log_warning(f"  - {param_name} = ERROR: {str(e)}")
            except Exception as e:
                unreal.log_error(f"Could not get static switch parameters: {str(e)}")
            
            # Texture parameters
            try:
                texture_params = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_names(material)
                unreal.log(f"TEXTURE PARAMETERS ({len(texture_params)}):")
                for param_name in texture_params:
                    try:
                        value = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(material, param_name)
                        param_str = str(param_name)
                        texture_name = value.get_name() if value else "None"
                        unreal.log(f"  - {param_str} = {texture_name}")
                    except Exception as e:
                        unreal.log_warning(f"  - {param_name} = ERROR: {str(e)}")
            except Exception as e:
                unreal.log_error(f"Could not get texture parameters: {str(e)}")
            
            unreal.log(f"=== END PARAMETER DISCOVERY FOR {material_name} ===")
            
        except Exception as e:
            unreal.log_error(f"Error during parameter discovery: {str(e)}")


# Create and run the importer
if __name__ == "__main__":
    # Only auto-run when executed as a script, so imports/reloads don't trigger twice
    importer = BlenderSyncUEImport()
    importer.run()

# DEBUGGING OPTIONS - Uncomment the lines you need:

# 1. To discover ALL parameters in your BlendSync materials (helpful for debugging):
# importer.discover_all_material_parameters()

# 2. To fix UV mapping issues in existing BlendSync materials:
# importer.fix_existing_materials_uv_mapping()

# 3. To analyze UV mapping issues in your BlendSync assets:
# importer.analyze_uv_mapping_issues()
