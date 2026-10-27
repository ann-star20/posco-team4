import bpy,os,math
from mathutils import Vector
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
base=os.path.dirname(__file__)
def mat(n,c,metal=0):
 m=bpy.data.materials.new(n);m.use_nodes=True;p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=.4;return m
white=mat('Fab_Wall_White',(.82,.88,.90));floor=mat('Fab_Floor',(.40,.54,.57),.15);blue=mat('Zone_Blue',(.02,.28,.55));green=mat('Zone_Green',(.02,.40,.18));trim=mat('Fab_Trim',(.35,.43,.48),.6)
shell=bpy.data.objects.new('Small_Fab_Shell_16x12m',None);bpy.context.collection.objects.link(shell)
def box(n,loc,dims,m,par=shell):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m);return o
box('Floor_16x12m',(0,0,-.10),(16,12,.20),floor)
box('Rear_Wall',(0,6,2.25),(16,.12,4.5),white);box('Left_Wall',(-8,0,2.25),(.12,12,4.5),white)
cut=bpy.data.collections.new('Front_Right_Walls_Hidden_For_Overview');bpy.context.scene.collection.children.link(cut)
for n,loc,d in [('Front_Wall',(0,-6,2.25),(16,.12,4.5)),('Right_Wall',(8,0,2.25),(.12,12,4.5))]:
 o=box(n,loc,d,white);bpy.context.collection.objects.unlink(o);cut.objects.link(o)
cut.hide_render=True;cut.hide_viewport=True
ceiling=bpy.data.collections.new('Ceiling_FFU_Hidden_For_Overview');bpy.context.scene.collection.children.link(ceiling)
for x in range(-7,8,2):
 for y in range(-5,6,2):
  for n,z,d,m in [('Ceiling_Panel',4.47,(1.94,1.94,.06),white),('FFU_Filter',4.42,(.95,.60,.035),trim)]:
   o=box(n,(x,y,z),d,m);bpy.context.collection.objects.unlink(o);ceiling.objects.link(o)
ceiling.hide_render=True;ceiling.hide_viewport=True
for x in range(-7,8):box('Rear_Panel_Joint',(x,5.93,2.25),(.012,.01,4.35),trim)
for y in (-2.05,-.55):box('Central_Aisle_Edge',(0,y,.008),(15,.055,.012),blue)
box('Inspection_Zone_Edge',(0,-4.65,.008),(15,.055,.012),green)
report=[]
for filename,rootname,cx,front,yaw in [('EFEM','EFEM_ROOT',-4.75,-.35,0),('Oxidation_Furnace','Oxidation_Furnace_ROOT',-.8,-.35,0),('Ion_Implanter','Ion_Implanter',3.6,-.35,math.pi/2),('Molding_Machine','Molding_Machine_ROOT',-4.45,-4.25,0),('AOI_Inspection_Line','AOI_Inspection_Line',3.25,-4.35,0)]:
 with bpy.data.libraries.load(os.path.join(base,filename+'.blend'),link=False) as (src,dst):dst.objects=src.objects
 loaded=[o for o in dst.objects if o];root=next(o for o in loaded if o.name==rootname)
 objects=[root]+list(root.children_recursive)
 for o in objects:
  if o.name.startswith('Preview_'):continue
  bpy.context.collection.objects.link(o)
  if filename=='EFEM' and o.name.startswith('FOUP_'):o.hide_render=True
 root.location=(0,0,0);root.rotation_euler.z=yaw
 bpy.context.view_layer.update()
 verts=[o.matrix_world@Vector(v) for o in objects if o.type in {'MESH','FONT'} and not o.hide_render and not o.name.startswith('Preview_') for v in o.bound_box]
 lo=Vector(tuple(min(v[i] for v in verts) for i in range(3)));hi=Vector(tuple(max(v[i] for v in verts) for i in range(3)))
 root.location+=Vector((cx-(lo.x+hi.x)/2,front-lo.y,-lo.z))
 bpy.context.view_layer.update()
 report.append((filename,tuple(hi-lo)))
 print('PLACED',filename,tuple(hi-lo))
 assert lo.x+root.location.x>=-7.95 and hi.x+root.location.x<=7.95,filename+' X exceeds room'
 assert hi.y+root.location.y<=5.95,filename+' rear exceeds room'
 # Remove unlinked preview and lighting objects loaded from asset files.
 for o in loaded:
  if o.users==0:bpy.data.objects.remove(o)
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=1500;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
bpy.ops.object.camera_add(location=(18,-21,19));cam=bpy.context.object;cam.name='Fab_Overview';cam.rotation_euler=(Vector((0,0,.7))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=45;scene.camera=cam
for loc,energy,size in [((0,-3,10),4500,10),((-4,3,9),4000,8),((8,3,8),3500,7)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=energy;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,0))-o.location).to_track_quat('-Z','Y').to_euler()
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(base,'Small_Fab_Layout_preview.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'Small_Fab_Layout.blend'))
print('SMALL_FAB_LAYOUT_SAVED',report)
bpy.ops.render.render(write_still=True)
