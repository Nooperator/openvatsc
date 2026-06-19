"""
Title: OpenVAT 1.1.7 Encoder
Description: Encode and preview vertex animation textures
Author: Luke Stilson
Date: 2025-04-29
Version: 1.1.7

"""

import bpy

from . import props, operators, panels

classes = []
classes.extend(props.classes)
classes.extend(panels.classes)
classes.extend(operators.classes)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.openvat_111_settings = bpy.props.PointerProperty(type=props.OpenVAT111Settings)
    bpy.types.Scene.openvat_111_anim_data = bpy.props.CollectionProperty(type=props.OpenVAT111AnimationEntry)

def unregister():
    del bpy.types.Scene.openvat_111_anim_data
    del bpy.types.Scene.openvat_111_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
