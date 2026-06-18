import importlib
import sys

import bpy


def get_openvat_utils_module():
    module_names = []

    if __package__:
        module_names.append(f"{__package__}.utils")

    module_names.extend([
        "bl_ext.user_default.openvat_111.utils",
        "bl_ext.system.openvat_111.utils",
        "openvat_111.utils",
        "openvat.utils",
    ])

    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ImportError:
            pass

    for module in list(sys.modules.values()):
        if getattr(module, "OPENVAT_BUILD_ID", "").startswith("openvat_111-"):
            return module

    raise RuntimeError("Could not find the enabled OpenVAT 1.1.x utils module.")


utils = get_openvat_utils_module()
utils.prepare_action_bake_timeline(bpy.context)
