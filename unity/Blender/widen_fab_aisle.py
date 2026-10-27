import bpy,os
base=os.path.dirname(__file__)
bpy.ops.wm.open_mainfile(filepath=os.path.join(base,'Small_Fab_Facing_Aisle.blend'))
for name in ('Molding_Machine_ROOT','AOI_Inspection_Line'):
 root=bpy.data.objects[name]
 root.location.y-=1.0
for o in bpy.data.objects:
 if o.name.startswith('Central_Aisle_Edge') and o.location.y < -1:
  o.location.y=-3.05
 if o.name=='Inspection_Zone_Edge':o.location.y=-5.65
bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
bpy.context.scene.render.filepath=os.path.join(base,'Small_Fab_Facing_Aisle_preview.png')
print('AISLE_WIDENED_TO_2_5M; front equipment row moved back 1m')
bpy.ops.render.render(write_still=True)
