import bpy

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

CLEAR_EXISTING_VAT_DATA = True


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def get_action_manual_range(action):
    if not hasattr(action, "use_frame_range"):
        return None, None, "manual frame range flag is unavailable"

    if not action.use_frame_range:
        return None, None, "manual frame range is disabled"

    if not hasattr(action, "frame_start") or not hasattr(action, "frame_end"):
        return None, None, "manual frame range values are unavailable"

    try:
        start_frame = round(action.frame_start)
        end_frame = round(action.frame_end)
    except TypeError:
        return None, None, "manual frame range values are invalid"

    if end_frame < start_frame:
        return None, None, f"end frame {end_frame} is before start frame {start_frame}"

    return start_frame, end_frame, None


def get_valid_actions():
    valid_actions = []
    skipped_actions = []

    for action in bpy.data.actions:
        start_frame, end_frame, skip_reason = get_action_manual_range(action)

        if skip_reason:
            skipped_actions.append({
                "name": action.name,
                "reason": skip_reason,
            })
            continue

        valid_actions.append({
            "action": action,
            "start_frame": start_frame,
            "end_frame": end_frame,
        })

    valid_actions.sort(key=lambda item: (
        item["start_frame"],
        item["end_frame"],
        item["action"].name,
    ))

    return valid_actions, skipped_actions


def print_skipped_actions(skipped_actions):
    if not skipped_actions:
        return

    print(f"Skipped {len(skipped_actions)} Action(s):")
    for item in skipped_actions:
        print(f"  - {item['name']}: {item['reason']}")


def clear_vat_anim_data(scene):
    data = scene.vat_anim_data

    # CollectionProperty normally supports clear() in modern Blender.
    if hasattr(data, "clear"):
        data.clear()
    else:
        while len(data) > 0:
            data.remove(0)


def add_vat_entry(scene, name, start_frame, end_frame):
    entry = scene.vat_anim_data.add()
    entry.name = name
    entry.start_frame = int(start_frame)
    entry.end_frame = int(end_frame)
    return entry


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

scene = bpy.context.scene
valid_actions, skipped_actions = get_valid_actions()

if not valid_actions:
    print_skipped_actions(skipped_actions)
    raise RuntimeError("No Actions with valid manual frame ranges found.")

if CLEAR_EXISTING_VAT_DATA:
    clear_vat_anim_data(scene)

for item in valid_actions:
    action = item["action"]
    add_vat_entry(
        scene,
        action.name,
        item["start_frame"],
        item["end_frame"],
    )

scene.frame_start = min(item["start_frame"] for item in valid_actions)
scene.frame_end = max(item["end_frame"] for item in valid_actions)

print_skipped_actions(skipped_actions)
print("Action frame range VAT metadata population complete.")
print(f"Created {len(valid_actions)} VAT animation entries.")
print(f"Timeline range: {scene.frame_start} - {scene.frame_end}")
