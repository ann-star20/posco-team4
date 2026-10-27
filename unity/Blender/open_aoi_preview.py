import bpy
from mathutils import Quaternion
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':
   area.spaces.active.shading.type='MATERIAL'
   area.spaces.active.overlay.show_extras=False
   area.spaces.active.region_3d.view_location=(0,0,1)
   area.spaces.active.region_3d.view_distance=7.5
   area.spaces.active.region_3d.view_rotation=Quaternion((0.89,0.35,0.12,0.24)).normalized()
try:
 bpy.context.scene.blendermcp_auto_start_server=True
 bpy.ops.blendermcp.start_server()
except Exception as exc:print(exc)
