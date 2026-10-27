import bpy,os,math
from mathutils import Vector
base=os.path.dirname(__file__)
bpy.ops.wm.open_mainfile(filepath=os.path.join(base,'Small_Fab_Layout.blend'))
def place(name,cx,edge,yaw,front_row=False):
 root=bpy.data.objects[name];root.location=(0,0,0);root.rotation_euler.z=yaw
 bpy.context.view_layer.update()
 vertices=[o.matrix_world@Vector(v) for o in root.children_recursive if o.type in {'MESH','FONT'} and not o.hide_render and not o.name.startswith('Preview_') for v in o.bound_box]
 lo=Vector(tuple(min(v[i] for v in vertices) for i in range(3)));hi=Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
 y=edge-hi.y if front_row else edge-lo.y
 root.location=((cx-(lo.x+hi.x)/2),y,-lo.z)
 bpy.context.view_layer.update()
 print(name,'rotation',yaw,'extents',tuple(hi-lo),'position',tuple(root.location))
place('Ion_Implanter',3.60,-.35,0)
place('Molding_Machine_ROOT',-4.45,-2.05,math.pi,True)
place('AOI_Inspection_Line',3.25,-2.05,math.pi,True)
bpy.context.scene.render.filepath=os.path.join(base,'Small_Fab_Facing_Aisle_preview.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'Small_Fab_Facing_Aisle.blend'))
bpy.ops.render.render(write_still=True)
