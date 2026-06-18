"""
Title: OpenVAT 1.1.1 Encoder
Description: Encode and preview vertex animation textures
Author: Luke Stilson
Date: 2025-04-29
Version: 1.1.1

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

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.openvat_111_settings


if __name__ == "__main__":
    register()
