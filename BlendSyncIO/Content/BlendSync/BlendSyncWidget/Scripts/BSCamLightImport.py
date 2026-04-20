from pathlib import Path
from typing import Optional, List, Tuple
import shutil

try:
    import unreal
except ImportError:
    unreal = None  # Script must run inside Unreal Editor


class BlendSyncUsdStageLoader57:
    """
    Open the latest BlendSync lights/cameras USD in the USD Stage Editor (UE 5.7 preview),
    mirror the imported actors into standalone level actors, and optionally close the Stage Editor.
    """

    PREFERRED_FILENAME = "BlendSyncLightsAndCameras.usd"
    SUPPORTED_EXTENSIONS = (".usd", ".usda", ".usdc")

    def __init__(self):
        if unreal is None:
            raise RuntimeError("This script requires Unreal Editor's Python environment.")

        project_dir = Path(unreal.Paths.project_dir())
        self.usd_root = project_dir / "BlendSyncIO" / "Unreal"

    def run(self, mirror_imports: bool = True, close_stage: bool = True,
            remove_stage_actor: bool = True, remove_root_wrappers: bool = True):
        stage_lib = getattr(unreal, "UsdStageEditorLibrary", None)
        if stage_lib is None:
            unreal.log_error("USD Stage Editor functionality is unavailable; enable the USDImporter plugin.")
            return

        usd_path = self._resolve_usd_path()
        if usd_path is None:
            unreal.log_warning(
                f"No USD files found in '{self.usd_root}'. Export lights/cameras from Blender first."
            )
            return

        usd_path_str = str(usd_path)

        try:
            stage_lib.open_stage_editor()
        except Exception:
            pass

        try:
            stage_lib.file_close()
        except Exception:
            pass

        try:
            stage_lib.file_open(usd_path_str)
            unreal.log(f"USD Stage Editor opened: {usd_path_str}")
        except Exception as exc:
            unreal.log_error(f"Failed to open USD stage '{usd_path_str}': {exc}")
            return

        stage_actor = None
        try:
            stage_actor = stage_lib.get_attached_stage_actor()
        except Exception:
            stage_actor = None

        if stage_actor:
            try:
                stage_actor.set_editor_property("root_layer", unreal.FilePath(usd_path_str))
                reload_fn = getattr(stage_actor, "reload_stage", None)
                if callable(reload_fn):
                    reload_fn()
                unreal.log(f"Stage actor '{stage_actor.get_actor_label()}' now points to {usd_path_str}")
            except Exception as exc:
                unreal.log_warning(f"Could not update stage actor root layer: {exc}")

            if mirror_imports:
                self._mirror_imported_actors(stage_actor, remove_stage_actor, remove_root_wrappers)
        else:
            unreal.log_warning("No stage actor is currently attached to the USD Stage Editor.")

        if close_stage:
            self.close()

    def close(self):
        stage_lib = getattr(unreal, "UsdStageEditorLibrary", None)
        if stage_lib is None:
            return

        try:
            stage_lib.file_close()
        except Exception:
            pass

        try:
            stage_lib.close_stage_editor()
            unreal.log("USD Stage Editor closed.")
        except Exception:
            pass

    def _resolve_usd_path(self) -> Optional[Path]:
        if not self.usd_root.exists():
            return None

        preferred = self.usd_root / self.PREFERRED_FILENAME
        if preferred.exists():
            return preferred.resolve()

        candidates = [
            path for path in self.usd_root.glob("*")
            if path.suffix.lower() in self.SUPPORTED_EXTENSIONS and path.is_file()
        ]
        if not candidates:
            return None

        return max(candidates, key=lambda path: path.stat().st_mtime).resolve()

    def _mirror_imported_actors(self, stage_actor, remove_stage_actor: bool, remove_root_wrappers: bool):
        actors_to_copy = self._collect_imported_actors(stage_actor)
        new_actors: List[Tuple[unreal.Actor, unreal.Actor]] = []
        if not actors_to_copy:
            unreal.log_warning("No child actors found under the imported USD Stage Actor.")
        else:
            for source_actor in actors_to_copy:
                duplicated = self._duplicate_actor(source_actor)
                if duplicated:
                    new_actors.append((source_actor, duplicated))

        hdri_asset = self._ensure_hdri_asset()
        for source_actor, new_actor in new_actors:
            self._maybe_configure_env_light(source_actor, new_actor, hdri_asset)

        if remove_root_wrappers:
            self._destroy_root_wrappers(stage_actor)

        if remove_stage_actor:
            self._destroy_actor_safe(stage_actor)

        self._clear_import_directory()

    def _collect_imported_actors(self, stage_actor):
        collected = []
        stack = []
        try:
            stack = list(stage_actor.get_attached_actors())
        except Exception:
            stack = []

        while stack:
            actor = stack.pop()
            try:
                children = list(actor.get_attached_actors())
            except Exception:
                children = []
            stack.extend(children)

            label = ""
            try:
                label = actor.get_actor_label()
            except Exception:
                label = ""

            if label.lower() == "root":
                continue
            collected.append(actor)

        return collected

    def _duplicate_actor(self, source_actor):
        label = "Unknown"
        try:
            label = source_actor.get_actor_label()
        except Exception:
            label = "Unknown"

        try:
            actor_class = source_actor.get_class()
            location = source_actor.get_actor_location()
            rotation = source_actor.get_actor_rotation()
            scale = source_actor.get_actor_scale3d()

            existing_actor = self._find_actor_by_label(label)
            if existing_actor:
                unreal.EditorLevelLibrary.destroy_actor(existing_actor)
                unreal.log(f"Existing actor '{label}' removed before import.")

            new_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(actor_class, location, rotation)
            if new_actor is None:
                return None

            try:
                new_actor.set_actor_scale3d(scale)
            except Exception:
                pass

            util_lib = getattr(unreal, "EditorUtilityLibrary", None)
            if util_lib and hasattr(util_lib, "copy_properties_for_unrelated_objects"):
                try:
                    util_lib.copy_properties_for_unrelated_objects(source_actor, new_actor)
                except Exception:
                    pass

            self._copy_light_components(source_actor, new_actor)
            self._copy_camera_components(source_actor, new_actor)

            try:
                folder = source_actor.get_folder_path()
                new_actor.set_folder_path(folder)
            except Exception:
                pass

            try:
                if label:
                    new_actor.set_actor_label(label)
            except Exception:
                pass

            unreal.log(f"Mirrored actor '{label}'")
            return new_actor
        except Exception as exc:
            unreal.log_warning(f"Could not duplicate actor '{label}': {exc}")
            return None

    def _destroy_root_wrappers(self, stage_actor):
        try:
            candidate_roots = list(stage_actor.get_attached_actors())
        except Exception:
            candidate_roots = []

        for actor in candidate_roots:
            label = ""
            try:
                label = actor.get_actor_label()
            except Exception:
                label = ""
            if label.lower() == "root":
                self._destroy_actor_safe(actor)

    @staticmethod
    def _destroy_actor_safe(actor):
        try:
            unreal.EditorLevelLibrary.destroy_actor(actor)
        except Exception as exc:
            label = "Unknown"
            try:
                label = actor.get_actor_label()
            except Exception:
                pass
            unreal.log_warning(f"Could not destroy actor '{label}': {exc}")

    @staticmethod
    def _find_actor_by_label(label: str):
        try:
            actors = unreal.EditorLevelLibrary.get_all_level_actors()
        except Exception:
            return None

        for actor in actors:
            try:
                actor_label = actor.get_actor_label()
            except Exception:
                continue
            if actor_label == label:
                return actor
        return None

    def _copy_light_components(self, source_actor, new_actor):
        light_class = getattr(unreal, "LightComponent", None)
        if light_class is None:
            return

        try:
            source_lights = source_actor.get_components_by_class(light_class)
            target_lights = new_actor.get_components_by_class(light_class)
        except Exception:
            return

        for index, source_comp in enumerate(source_lights or []):
            if index >= len(target_lights or []):
                break
            target_comp = target_lights[index]

            util_lib = getattr(unreal, "EditorUtilityLibrary", None)
            if util_lib and hasattr(util_lib, "copy_properties_for_unrelated_objects"):
                try:
                    util_lib.copy_properties_for_unrelated_objects(source_comp, target_comp)
                except Exception:
                    pass

            for prop in (
                "light_color",
                "intensity",
                "use_temperature",
                "temperature",
                "indirect_lighting_intensity",
                "volumetric_scattering_intensity",
                "attenuation_radius",
                "source_radius",
                "soft_source_radius",
                "source_length",
                "source_width",
                "source_height",
                "inner_cone_angle",
                "outer_cone_angle",
                "source_angle",
                "source_soft_angle",
                "barn_door_angle",
                "barn_door_length",
            ):
                try:
                    value = source_comp.get_editor_property(prop)
                    target_comp.set_editor_property(prop, value)
                except Exception:
                    continue

    def _copy_camera_components(self, source_actor, new_actor):
        camera_classes = []
        for class_name in ("CineCameraComponent", "CameraComponent"):
            cls = getattr(unreal, class_name, None)
            if cls is not None:
                camera_classes.append(cls)

        if not camera_classes:
            return

        util_lib = getattr(unreal, "EditorUtilityLibrary", None)
        copy_props = getattr(util_lib, "copy_properties_for_unrelated_objects", None) if util_lib else None

        for camera_class in camera_classes:
            try:
                source_components = source_actor.get_components_by_class(camera_class)
                target_components = new_actor.get_components_by_class(camera_class)
            except Exception:
                continue

            for index, source_comp in enumerate(source_components or []):
                if index >= len(target_components or []):
                    break

                target_comp = target_components[index]
                label = "Camera"
                try:
                    label = new_actor.get_actor_label()
                except Exception:
                    pass

                if callable(copy_props):
                    try:
                        copy_props(source_comp, target_comp)
                    except Exception:
                        pass

                try:
                    target_comp.set_editor_property("manual_focus_distance",
                                                    source_comp.get_editor_property("manual_focus_distance"))
                except Exception:
                    pass

                cine_comp = getattr(unreal, "CineCameraComponent", None)
                if cine_comp and isinstance(target_comp, cine_comp):
                    try:
                        filmback_struct = None
                        if hasattr(source_comp, "get_editor_property"):
                            try:
                                filmback_struct = source_comp.get_editor_property("filmback")
                            except Exception:
                                filmback_struct = None
                        if filmback_struct is None:
                            filmback_struct = unreal.CameraFilmbackSettings()
                            filmback_struct.sensor_width = source_comp.get_editor_property("sensor_width")
                            filmback_struct.sensor_height = source_comp.get_editor_property("sensor_height")

                        target_comp.set_editor_property("filmback", filmback_struct)
                        try:
                            target_comp.set_editor_property("sensor_width", filmback_struct.sensor_width)
                            target_comp.set_editor_property("sensor_height", filmback_struct.sensor_height)
                        except Exception:
                            pass

                        for bool_prop in (
                            "override_filmback_settings",
                            "override_camera_filmback",
                            "use_manual_filmback",
                            "use_manual_sensor",
                        ):
                            if hasattr(target_comp, "has_editor_property") and target_comp.has_editor_property(bool_prop):
                                try:
                                    target_comp.set_editor_property(bool_prop, True)
                                except Exception:
                                    pass

                        unreal.log(
                            f"Filmback copy '{label}': {filmback_struct.sensor_width}x{filmback_struct.sensor_height}"
                        )
                    except Exception as cine_exc:
                        unreal.log_warning(f"Failed to copy CineCamera filmback for {label}: {cine_exc}")
                else:
                    try:
                        filmback_settings = None
                        if hasattr(source_comp, "get_editor_property"):
                            try:
                                filmback_settings = source_comp.get_editor_property("filmback")
                            except Exception:
                                filmback_settings = source_comp.get_editor_property("filmback_settings")
                        if filmback_settings is not None:
                            target_comp.set_editor_property("filmback", filmback_settings)
                            try:
                                target_comp.set_editor_property("sensor_width", getattr(filmback_settings, "sensor_width", None))
                                target_comp.set_editor_property("sensor_height", getattr(filmback_settings, "sensor_height", None))
                            except Exception:
                                pass
                            for bool_prop in (
                                "override_filmback_settings",
                                "override_camera_filmback",
                                "use_manual_filmback",
                                "use_manual_sensor",
                            ):
                                if hasattr(target_comp, "has_editor_property") and target_comp.has_editor_property(bool_prop):
                                    try:
                                        target_comp.set_editor_property(bool_prop, True)
                                    except Exception:
                                        pass
                            unreal.log(
                                f"Filmback copy '{label}': "
                                f"{getattr(filmback_settings, 'sensor_width', 'n/a')}x{getattr(filmback_settings, 'sensor_height', 'n/a')}"
                            )
                        else:
                            raise AttributeError("filmback data missing")
                    except Exception as exc:
                        unreal.log_warning(f"Failed to copy filmback for {label}: {exc}")

                try:
                    lens_settings = source_comp.get_editor_property("lens_settings")
                    target_comp.set_editor_property("lens_settings", lens_settings)
                except Exception:
                    pass

                try:
                    focus_settings = source_comp.get_editor_property("focus_settings")
                    target_comp.set_editor_property("focus_settings", focus_settings)
                except Exception:
                    pass

                env_props = (
                    "current_focal_length",
                    "current_aperture",
                    "sensor_width",
                    "sensor_height",
                    "aspect_ratio",
                    "field_of_view",
                    "manual_focus_distance",
                )
                debug_values = []
                for prop in env_props:
                    try:
                        value = source_comp.get_editor_property(prop)
                        target_comp.set_editor_property(prop, value)
                        debug_values.append(f"{prop}={value}")
                    except Exception:
                        continue

                if debug_values:
                    try:
                        label = new_actor.get_actor_label()
                    except Exception:
                        label = "Camera"
                    try:
                        unreal.log(f"Camera '{label}' properties copied: " + ", ".join(debug_values))
                    except Exception:
                        pass

    def _ensure_hdri_asset(self):
        textures_dir = self.usd_root / "Textures"
        if not textures_dir.exists():
            return None

        hdri_candidates = [
            path for path in textures_dir.glob("*")
            if path.suffix.lower() in {".hdr", ".exr"} and path.is_file()
        ]
        if not hdri_candidates:
            return None

        hdri_file = max(hdri_candidates, key=lambda path: path.stat().st_mtime)

        content_dir = Path(unreal.Paths.project_content_dir())
        destination_dir = content_dir / "BlendSync" / "HDRI"
        destination_dir.mkdir(parents=True, exist_ok=True)

        destination_file = destination_dir / hdri_file.name
        try:
            shutil.copy2(hdri_file, destination_file)
        except Exception as exc:
            unreal.log_warning(f"Failed to copy HDRI '{hdri_file}' to project HDRI folder: {exc}")
            return None

        asset_path = f"/Game/BlendSync/HDRI/{hdri_file.stem}"

        try:
            if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
                return unreal.EditorAssetLibrary.load_asset(asset_path)
        except Exception:
            pass

        try:
            task = unreal.AssetImportTask()
            task.automated = True
            task.replace_existing = True
            task.filename = str(destination_file)
            task.destination_path = "/Game/BlendSync/HDRI"
            task.destination_name = hdri_file.stem
            task.save = True

            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            imported_paths = task.get_editor_property("imported_object_paths")
            if imported_paths:
                return unreal.EditorAssetLibrary.load_asset(imported_paths[0])
        except Exception as exc:
            unreal.log_warning(f"Failed to import HDRI asset '{destination_file}': {exc}")

        return None

    def _maybe_configure_env_light(self, source_actor, new_actor, hdri_asset):
        if hdri_asset is None:
            return

        label = ""
        try:
            label = (new_actor.get_actor_label() or "").lower()
        except Exception:
            label = ""

        if label != "env_light":
            return

        skylight_class = getattr(unreal, "SkyLightComponent", None)
        if skylight_class is None:
            return

        skylight = None
        try:
            skylight = new_actor.get_component_by_class(skylight_class)
        except Exception:
            skylight = None

        if skylight is None:
            return

        try:
            source_type_enum = getattr(unreal, "SkyLightSourceType", None)
            if source_type_enum is not None and hasattr(source_type_enum, "SLS_SPECIFIED_CUBEMAP"):
                skylight.set_editor_property("source_type", source_type_enum.SLS_SPECIFIED_CUBEMAP)
        except Exception:
            pass

        try:
            skylight.set_editor_property("cubemap", hdri_asset)
        except Exception:
            pass

        for res_prop in ("cubemap_resolution", "source_cubemap_resolution"):
            try:
                skylight.set_editor_property(res_prop, 512)
                break
            except Exception:
                continue

        recapture = getattr(skylight, "recapture_sky", None)
        if callable(recapture):
            try:
                recapture()
            except Exception:
                pass

    def _clear_import_directory(self):
        if not self.usd_root.exists():
            return

        for path in self.usd_root.iterdir():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except Exception:
                    pass


def close_stage_editor():
    BlendSyncUsdStageLoader57().close()


def detach_stage_actor_children(remove_stage_actor: bool = True, remove_root: bool = True):
    loader = BlendSyncUsdStageLoader57()
    loader.run(mirror_imports=True, close_stage=False,
               remove_stage_actor=remove_stage_actor,
               remove_root_wrappers=remove_root)


def execute():
    loader = BlendSyncUsdStageLoader57()
    loader.run(mirror_imports=True, close_stage=True,
               remove_stage_actor=True, remove_root_wrappers=True)


execute()


