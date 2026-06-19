# OpenVAT Utility Functions

import bpy
import json
import math
import bmesh
import os

NODE_GROUPS_BLEND_FILE = os.path.join(os.path.dirname(__file__), "vat_node_groups.blend")
OPENVAT_BUILD_ID = "openvat_111-1.1.7"
NODE_GROUP_ALIASES = {
    "ov_generated-pos": "ov111_generated-pos",
    "ov_vat-decoder-vs": "ov111_vat-decoder-vs",
    "ov_calculate-position-vs": "ov111_calculate-position-vs",
}
ACTION_BAKE_START_FRAME = 1
ACTION_BAKE_GAP_FRAMES = 0
ACTION_BAKE_TRACK_NAME = "OpenVAT111_ActionBake"

def get_animation_owner_name(owner):
    if hasattr(owner, "id_data") and owner.id_data != owner:
        return f"{owner.id_data.name}:{owner.name}"
    return getattr(owner, "name", str(owner))

def get_action_manual_range(action):
    if getattr(action, "use_frame_range", None) is False:
        return None, None, "manual frame range is disabled"

    try:
        if hasattr(action, "frame_start") and hasattr(action, "frame_end"):
            start_frame = round(action.frame_start)
            end_frame = round(action.frame_end)
        elif hasattr(action, "frame_range"):
            start_frame = round(action.frame_range[0])
            end_frame = round(action.frame_range[1])
        else:
            return None, None, "frame range values are unavailable"
    except (TypeError, IndexError):
        return None, None, "manual frame range values are invalid"

    if end_frame < start_frame:
        return None, None, f"end frame {end_frame} is before start frame {start_frame}"

    return int(start_frame), int(end_frame), None

def action_targets_armature(action):
    if getattr(action, "id_root", None) == 'ARMATURE':
        return True

    return any(
        fc.data_path.startswith("pose.bones")
        for fc in getattr(action, "fcurves", [])
    )

def action_targets_shape_keys(action):
    if getattr(action, "id_root", None) == 'KEY':
        return True

    return any(
        fc.data_path.startswith("key_blocks")
        for fc in getattr(action, "fcurves", [])
    )

def add_unique_id(items, item):
    if not item:
        return

    pointer = item.as_pointer() if hasattr(item, "as_pointer") else id(item)
    if pointer not in {existing.as_pointer() if hasattr(existing, "as_pointer") else id(existing) for existing in items}:
        items.append(item)

def get_action_bake_objects(context):
    scene = context.scene
    settings = getattr(scene, "openvat_111_settings", None)
    objects = []

    if (
        settings
        and getattr(settings, "encode_target", None) == 'COLLECTION_COMBINE'
        and getattr(settings, "vat_collection", None)
    ):
        for obj in settings.vat_collection.all_objects:
            add_unique_id(objects, obj)
    else:
        add_unique_id(objects, context.object)
        for obj in context.selected_objects:
            add_unique_id(objects, obj)

    for obj in list(objects):
        if obj and obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'ARMATURE':
                    add_unique_id(objects, mod.object)

    return objects

def get_action_bake_owners(context):
    owners = []

    for obj in get_action_bake_objects(context):
        add_unique_id(owners, obj)
        if obj and obj.type == 'MESH' and obj.data and obj.data.shape_keys:
            add_unique_id(owners, obj.data.shape_keys)

    return owners

def animation_owner_uses_action(owner, action):
    anim_data = getattr(owner, "animation_data", None)
    if not anim_data:
        return False

    if getattr(anim_data, "action", None) == action:
        return True

    for track in getattr(anim_data, "nla_tracks", []):
        for strip in track.strips:
            if strip.action == action:
                return True

    return False

def is_armature_animation_owner(owner):
    return isinstance(owner, bpy.types.Object) and owner.type == 'ARMATURE'

def is_shape_key_animation_owner(owner):
    return isinstance(owner, bpy.types.Key)

def preferred_owner_for_action(action, owners):
    assigned_owners = [
        owner for owner in owners
        if animation_owner_uses_action(owner, action)
    ]

    if assigned_owners:
        if action_targets_armature(action):
            for owner in assigned_owners:
                if is_armature_animation_owner(owner):
                    return owner
        if action_targets_shape_keys(action):
            for owner in assigned_owners:
                if is_shape_key_animation_owner(owner):
                    return owner
        return assigned_owners[0]

    if action_targets_armature(action):
        for owner in owners:
            if is_armature_animation_owner(owner):
                return owner
        return None

    if action_targets_shape_keys(action):
        for owner in owners:
            if is_shape_key_animation_owner(owner):
                return owner
        return None

    active = bpy.context.object
    if active in owners:
        return active

    for owner in owners:
        if isinstance(owner, bpy.types.Object):
            return owner

    return owners[0] if owners else None

def get_valid_action_items(context):
    valid_items = []
    skipped_actions = []
    owners = get_action_bake_owners(context)

    for action in bpy.data.actions:
        start_frame, end_frame, skip_reason = get_action_manual_range(action)

        if skip_reason:
            skipped_actions.append({
                "name": action.name,
                "reason": skip_reason,
            })
            continue

        target = preferred_owner_for_action(action, owners)
        if not target:
            skipped_actions.append({
                "name": action.name,
                "reason": "no compatible target object or animation owner found",
            })
            continue

        valid_items.append({
            "action": action,
            "target": target,
            "source_start": start_frame,
            "source_end": end_frame,
        })

    valid_items.sort(key=lambda item: (
        item["action"].name.casefold(),
        item["action"].name,
        item["source_start"],
        item["source_end"],
    ))

    return valid_items, skipped_actions

def print_skipped_actions(skipped_actions):
    if not skipped_actions:
        return

    print(f"Skipped {len(skipped_actions)} Action(s):")
    for item in skipped_actions:
        print(f"  - {item['name']}: {item['reason']}")

def get_unique_animation_owners(items):
    owners = []
    for item in items:
        add_unique_id(owners, item["target"])
    return owners

def clear_vat_anim_data(scene):
    data = get_vat_animation_entries(scene)

    if hasattr(data, "clear"):
        data.clear()
    else:
        while len(data) > 0:
            data.remove(0)

def add_vat_entry(scene, name, start_frame, end_frame):
    data = get_vat_animation_entries(scene)
    if not hasattr(data, "add"):
        raise RuntimeError("No VAT animation data collection is registered on the scene.")

    entry = data.add()
    entry.name = name
    entry.start_frame = int(start_frame)
    entry.end_frame = int(end_frame)
    if hasattr(entry, "framerate"):
        entry.framerate = get_scene_framerate(scene)
    if hasattr(entry, "looping"):
        entry.looping = True
    return entry

def ensure_animation_data(owner):
    owner.animation_data_create()
    return owner.animation_data

def remove_existing_action_bake_tracks(targets):
    for target in targets:
        anim_data = getattr(target, "animation_data", None)
        if not anim_data:
            continue

        for track in list(anim_data.nla_tracks):
            if track.name == ACTION_BAKE_TRACK_NAME:
                anim_data.nla_tracks.remove(track)

def get_or_create_action_bake_track(target):
    anim_data = ensure_animation_data(target)
    track = anim_data.nla_tracks.new()
    track.name = ACTION_BAKE_TRACK_NAME
    track.mute = False
    track.lock = False
    return track

def make_action_bake_strip(track, item, timeline_start, timeline_end):
    action = item["action"]
    source_start = item["source_start"]
    source_end = item["source_end"]
    strip_end = max(timeline_end, timeline_start + 1)

    strip = track.strips.new(action.name, timeline_start, action)
    strip.frame_start = timeline_start
    strip.frame_end = strip_end
    strip.action_frame_start = source_start
    strip.action_frame_end = max(source_end, source_start + 1)
    strip.repeat = 1.0
    strip.scale = 1.0
    strip.blend_type = 'REPLACE'
    strip.extrapolation = 'NOTHING'
    return strip

def layout_actions_for_bake(scene, valid_items):
    tracks_by_target = {}
    cursor = ACTION_BAKE_START_FRAME
    laid_out_items = []

    remove_existing_action_bake_tracks(get_unique_animation_owners(valid_items))

    for item in valid_items:
        target = item["target"]
        target_key = target.as_pointer() if hasattr(target, "as_pointer") else id(target)
        if target_key not in tracks_by_target:
            tracks_by_target[target_key] = get_or_create_action_bake_track(target)

        source_duration = item["source_end"] - item["source_start"]
        timeline_start = cursor
        timeline_end = cursor + source_duration

        make_action_bake_strip(tracks_by_target[target_key], item, timeline_start, timeline_end)
        ensure_animation_data(target).action = None

        laid_out_items.append({
            **item,
            "timeline_start": timeline_start,
            "timeline_end": timeline_end,
        })

        cursor = timeline_end + ACTION_BAKE_GAP_FRAMES + 1

    scene.frame_start = ACTION_BAKE_START_FRAME
    scene.frame_end = max(item["timeline_end"] for item in laid_out_items)

    return laid_out_items

def prepare_action_bake_timeline(context):
    scene = context.scene
    valid_items, skipped_actions = get_valid_action_items(context)

    if not valid_items:
        print_skipped_actions(skipped_actions)
        raise RuntimeError("No Actions with valid manual frame ranges and compatible targets found.")

    laid_out_items = layout_actions_for_bake(scene, valid_items)
    clear_vat_anim_data(scene)

    for item in laid_out_items:
        add_vat_entry(
            scene,
            item["action"].name,
            item["timeline_start"],
            item["timeline_end"],
        )

    print_skipped_actions(skipped_actions)
    print("Action-based VAT bake timeline prepared.")
    print(f"Created {len(laid_out_items)} VAT animation entries.")
    print(f"Timeline range: {scene.frame_start} - {scene.frame_end}")
    print(f"Created bake track '{ACTION_BAKE_TRACK_NAME}' on:")
    for target in get_unique_animation_owners(laid_out_items):
        print(f"  - {get_animation_owner_name(target)}")

    return laid_out_items

def append_node_group(group_name, target_name=None):
    target_name = target_name or group_name
    existing_groups = {group.name for group in bpy.data.node_groups}

    with bpy.data.libraries.load(NODE_GROUPS_BLEND_FILE, link=False) as (data_from, data_to):
        if group_name in data_from.node_groups:
            data_to.node_groups.append(group_name)
        else:
            raise RuntimeError(f"Node group '{group_name}' not found in {NODE_GROUPS_BLEND_FILE}")

    appended_groups = [
        group for group in bpy.data.node_groups
        if group.name not in existing_groups
    ]
    candidates = [
        group for group in appended_groups
        if group.name == group_name or group.name.startswith(f"{group_name}.")
    ]

    if not candidates:
        raise RuntimeError(f"Failed to append node group '{group_name}'")

    group = candidates[0]
    group.name = target_name
    return group

def ensure_node_group(group_name):
    local_name = NODE_GROUP_ALIASES.get(group_name, group_name)
    if local_name not in bpy.data.node_groups:
        return append_node_group(group_name, local_name)
    return bpy.data.node_groups[local_name]

def get_scene_framerate(scene):
    fps_base = getattr(scene.render, "fps_base", 1.0) or 1.0
    return scene.render.fps / fps_base

def get_action_frame_range(action):
    if hasattr(action, "frame_start") and hasattr(action, "frame_end"):
        start_frame = round(action.frame_start)
        end_frame = round(action.frame_end)
    elif hasattr(action, "frame_range"):
        start_frame = round(action.frame_range[0])
        end_frame = round(action.frame_range[1])
    else:
        return None

    if end_frame < start_frame:
        return None

    return int(start_frame), int(end_frame)

def get_vat_animation_entries(scene):
    if hasattr(scene, "openvat_111_anim_data"):
        return scene.openvat_111_anim_data
    if hasattr(scene, "vat_anim_data"):
        return scene.vat_anim_data
    return []

def make_animation_metadata(scene):
    animations = {}
    default_framerate = get_scene_framerate(scene)

    for entry in get_vat_animation_entries(scene):
        name = getattr(entry, "name", "").strip()
        if not name:
            continue

        animations[name] = {
            "startFrame": int(getattr(entry, "start_frame", 0)),
            "endFrame": int(getattr(entry, "end_frame", 0)),
            "framerate": float(getattr(entry, "framerate", default_framerate)),
            "looping": bool(getattr(entry, "looping", True)),
        }

    if animations:
        return animations

    for action in bpy.data.actions:
        frame_range = get_action_frame_range(action)
        if frame_range is None:
            continue

        start_frame, end_frame = frame_range

        animations[action.name] = {
            "startFrame": start_frame,
            "endFrame": end_frame,
            "framerate": float(default_framerate),
            "looping": True,
        }

    return animations

def add_animation_metadata(data, scene):
    data["_openvatBuild"] = OPENVAT_BUILD_ID
    animations = make_animation_metadata(scene)
    if animations:
        data["animations"] = animations
        print(f"Added {len(animations)} VAT animation metadata entr{'y' if len(animations) == 1 else 'ies'} to JSON")
    else:
        print("No VAT animation metadata entries found; JSON will use importer default animation")

def make_custom_data(obj_name, attr_names, frame_start, frame_end, output_filepath, remap_output_filepath):
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        print(f"Object '{obj_name}' not found")
        return

    frames = frame_end - frame_start + 1
    channel_remap_data = {}

    for attr in attr_names:
        if not attr or attr.upper() == "NONE":
            channel_remap_data["None"] = {
                "Min": 0.0,
                "Max": 0.0,
                "Frames": frames
            }
            continue

        frame_data = {}
        for frame in range(frame_start, frame_end + 1):
            bpy.context.scene.frame_set(frame)
            values = get_geometry_nodes_data(obj, attr)
            frame_data[frame] = values

        if not any(frame_data.values()):
            raise ValueError(f"No values were sampled for custom attribute '{attr}' on '{obj.name}'")

        attr_min, attr_max = find_scalar_max_min(frame_data)
        channel_remap_data[attr] = {
            "Min": attr_min,
            "Max": attr_max,
            "Frames": frames
        }

    add_animation_metadata(channel_remap_data, bpy.context.scene)

    # Write or return the remap info
    with open(remap_output_filepath, 'w') as f:
        json.dump(channel_remap_data, f, indent=4)

def make_remap_data(obj_name, attribute_name, frame_start, frame_end, output_filepath, remap_output_filepath, scalar_value):
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        print(f"Object '{obj_name}' not found")
        return
    
    # Remap data for vector properties
    all_frames_data = {}
    scalar_data = {}
    frames = frame_end - frame_start + 1

    for frame in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(frame)
        frame_data = get_geometry_nodes_data(obj, attribute_name)
        all_frames_data[frame] = frame_data

    if not any(all_frames_data.values()):
        raise ValueError(
            f"No values were sampled for attribute '{attribute_name}' on '{obj.name}'. "
            "Check that this build's Geometry Nodes groups loaded correctly."
        )

    overall_max, overall_min = find_max_min_values(all_frames_data)
    sampled_all_zero = (
        overall_min == [0.0, 0.0, 0.0]
        and overall_max == [0.0, 0.0, 0.0]
    )
    
    if attribute_name == "colPos":
        attribute_name = "os-remap"
        
    # Scalar value for alpha data
    if scalar_value:
        for frame in range(frame_start, frame_end + 1):
            bpy.context.scene.frame_set(frame)
            frame_data = get_geometry_nodes_data(obj, scalar_value)
            scalar_data[frame] = frame_data
        
        scalar_max, scalar_min = find_scalar_max_min(scalar_data)
        
        remap_info = {
            attribute_name: {
                "Min": overall_min,
                "Max": overall_max,
                "Frames": frames
            },
            scalar_value: {
                "Min": scalar_min,
                "Max": scalar_max,
            }
        }
    else:
        remap_info = {
            attribute_name: {
                "Min": overall_min,
                "Max": overall_max,
                "Frames": frames
            }
    }
    
    add_animation_metadata(remap_info, bpy.context.scene)
    if sampled_all_zero:
        remap_info["_openvatWarnings"] = [
            "Sampled position offsets are all zero. The encoded target appears static relative to the proxy over this frame range."
        ]
    write_json(remap_info, remap_output_filepath)
    print(f"Remap information saved to {remap_output_filepath}")

# Get data from dependency graph
def get_geometry_nodes_data(obj, attribute_name):
    data = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.data

    if attribute_name in mesh.attributes:
        attr = mesh.attributes[attribute_name]
        attr_data = attr.data

        if attr.domain not in {'POINT'}:
            print(f"Warning: Unsupported domain '{attr.domain}' for attribute '{attribute_name}'")

        for item in attr_data:
            if hasattr(item, 'vector'):
                data.append([round(val, 8) for val in item.vector])
            elif hasattr(item, 'value'):
                data.append(round(item.value, 8))
            else:
                print(f"Warning: Unknown attribute type for '{attribute_name}'")
    else:
        print(f"Attribute '{attribute_name}' not found in '{obj.name}'")

    return data


def write_json(data, filepath):
    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, float):
                return format(obj, ".8f")
            return json.JSONEncoder.default(self, obj)

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4, cls=CustomEncoder)

def apply_modifier(obj, modifier):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_from_eval = bpy.data.meshes.new_from_object(obj_eval)

    obj.modifiers.remove(modifier)
    obj.data = mesh_from_eval

def find_scalar_max_min(all_frames_data):
    max_value = float('-inf')
    min_value = float('inf')
    
    for frame, data in all_frames_data.items():
        for value in data:
            max_value = max(max_value, value)
            min_value = min(min_value, value)
    if max_value == float('-inf'):
        max_value = None
    if min_value == float('inf'):
        min_value = None

    if max_value is not None:
        max_value = round_to_nearest_ten(max_value, math.ceil)
    if min_value is not None:
        min_value = round_to_nearest_ten(min_value, math.floor)

    return min_value, max_value
            
# Function to find x, y, z min/max from JSON
def find_max_min_values(all_frames_data):
    max_values = [float('-inf'), float('-inf'), float('-inf')]
    min_values = [float('inf'), float('inf'), float('inf')]

    for frame, data in all_frames_data.items():
        for vector in data:
            for i in range(3):
                max_values[i] = max(max_values[i], vector[i])
                min_values[i] = min(min_values[i], vector[i])

    max_values = [val if val != float('-inf') else None for val in max_values]
    min_values = [val if val != float('inf') else None for val in min_values]

    overall_max = [round_to_nearest_ten(val, math.ceil) if val is not None else None for val in max_values]
    overall_min = [round_to_nearest_ten(val, math.floor) if val is not None else None for val in min_values]

    return overall_max, overall_min

def round_to_nearest_ten(val, func):
    return func(val * 10) / 10

def read_remap_info(filepath, attribute):
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    if attribute == "colPos":
        attribute = "os-remap"
    min_values = data[attribute]["Min"]
    max_values = data[attribute]["Max"]

    min_x, min_y, min_z = min_values
    max_x, max_y, max_z = max_values

    return min_x, min_y, min_z, max_x, max_y, max_z

def read_custom_info(filepath, attr_names):
    """
    Returns a flat list of min/max per attribute: [min_r, min_g, min_b, max_r, max_g, max_b]
    """
    with open(filepath, 'r') as f:
        data = json.load(f)

    min_vals = []
    max_vals = []

    for attr in attr_names:
        if not attr or attr.upper() == "NONE":
            min_vals.append(0.0)
            max_vals.append(0.0)
            continue
        
        if attr not in data:
            raise ValueError(f"Attribute '{attr}' not found in remap file.")

        min_vals.append(data[attr]["Min"])
        max_vals.append(data[attr]["Max"])


    return (*min_vals, *max_vals)

def clean_mesh_data(obj):

    if obj and obj.type == 'MESH':
        mesh = bpy.data.meshes.get(obj.data.name)
        color_attrs = [attr for attr in mesh.attributes if attr.data_type in {'FLOAT_COLOR', 'BYTE_COLOR'}]
        for attr in color_attrs:
            mesh.attributes.remove(attr)
        if mesh.shape_keys:
            key = mesh.shape_keys
            for block in list(key.key_blocks):
                key.key_blocks.remove(block)
            obj.shape_key_clear()
        while obj.vertex_groups:
            obj.vertex_groups.active_index = 0  # Set a valid active index
            obj.vertex_groups.remove(obj.vertex_groups[0])

# Calculation for estimating max amount of verts if all edges are ripped
def get_virtual_ripped_vertex_count(obj):
    if not obj or obj.type != 'MESH':
        return 0
    
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    count = len(eval_mesh.loops)
    eval_obj.to_mesh_clear()
    
    return count

# Best working approximations for output size based on realized data available

def calculate_optimal_vat_resolution(num_vertices, num_frames):
    def next_power_of_2(x):
        return 1 if x <= 1 else 2**math.ceil(math.log2(x))

    def powers_of_two(min_val=64, max_val=8192):
        val = min_val
        while val <= max_val:
            yield val
            val *= 2

    best = None
    best_area = float('inf')

    for width in powers_of_two():
        num_wraps = math.ceil(num_vertices / width)
        height_unrounded = num_frames * num_wraps
        height = next_power_of_2(height_unrounded)

        log2_width = math.log2(width)
        log2_height = math.log2(height)

        if abs(log2_width - log2_height) > 1:
            continue  # Skip if too far from square

        area = width * height
        if area < best_area:
            best = (width, height, num_wraps)
            best_area = area

    return best


def calculate_packed_vat_resolution(num_vertices, num_frames):
    def next_pow2(n):
        return 2 ** math.ceil(math.log2(n))

    def powers_of_two(min_val=64, max_val=8192):
        v = min_val
        while v <= max_val:
            yield v
            v *= 2

    best = None
    best_area = float('inf')

    for width in powers_of_two():
        num_wraps = math.ceil(num_vertices / width)

        pos_height = num_wraps * num_frames
        norm_height = num_wraps * num_frames
        total_height = next_pow2(pos_height + norm_height)

        log_w = math.log2(width)
        log_h = math.log2(total_height)

        if abs(log_w - log_h) > 1:
            continue

        area = width * total_height
        if area < best_area:
            best = (width, total_height, num_wraps)
            best_area = area

    return best

 
 
def rip_hard_edges(obj):
    if not obj or obj.type != 'MESH':
        raise Exception("Active object must be a mesh")

    mesh = obj.data

    depsgraph = bpy.context.evaluated_depsgraph_get() # Gets evaluated edges post-modifiers
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()

    sharp_edge_indices = {
        i for i, e in enumerate(eval_mesh.edges)
        if e.use_edge_sharp
    }
    eval_obj.to_mesh_clear()

    if obj.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    edges_to_split = []
    for i, e in enumerate(bm.edges):
        if i in sharp_edge_indices:
            edges_to_split.append(e)
            continue

        if not e.smooth:
            edges_to_split.append(e)
            continue

        linked_faces = e.link_faces
        if len(linked_faces) == 2:
            if not linked_faces[0].smooth and not linked_faces[1].smooth:
                edges_to_split.append(e)

    # Perform Edge Split
    bmesh.ops.split_edges(bm, edges=edges_to_split)

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()  
    
def get_point_attributes_filtered(self, context, data_type_filter=None):
    items = []
    obj = context.active_object
    if obj and obj.type == 'MESH':
        depsgraph = context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.data
        
        for attr in mesh.attributes:
            if attr.domain != 'POINT':
                continue
            if attr.name.startswith('.') or attr.name.startswith('_') or len(attr.name) > 32:
                continue
            if data_type_filter and attr.data_type != data_type_filter:
                continue
            items.append((attr.name, attr.name, ""))
                
    if not items:
        items.append(('None', 'None', 'No attributes found'))
        
    return items

def get_evaluated_point_float_attributes(context):
    depsgraph = context.evaluated_depsgraph_get()
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return []

    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        return [
            (attr.name, attr.name, "")
            for attr in eval_mesh.attributes
            if attr.domain == 'POINT' and attr.data_type == 'FLOAT'
        ]
    finally:
        eval_obj.to_mesh_clear()

_openvat_enum_cache = {
    "1": [("NONE", "None", "")],
    "2": [("NONE", "None", "")],
    "3": [("NONE", "None", "")]
}
