import bpy, math, os
from mathutils import Vector
base=os.path.dirname(__file__)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.unit_settings.length_unit='MILLIMETERS'
def mat(name,color,metal,rough):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
 p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
 return m
bodymat=mat('Molded_Black',(.014,.017,.022),0,.63)
steel=mat('Tin_Plated_Metal',(.58,.61,.64),.82,.28)
ink=mat('Laser_Marking',(.065,.07,.075),0,.72)
root=bpy.data.objects.new('MOSFET_D4184',None);scene.collection.objects.link(root)
def prism(name,outline,z0,z1,material):
 n=len(outline);v=[(x,y,z) for z in [z0,z1] for x,y in outline]
 f=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(v,[],f);mesh.update()
 o=bpy.data.objects.new(name,mesh);scene.collection.objects.link(o);o.parent=root;o.data.materials.append(material)
 bevel=o.modifiers.new('Soft_edges','BEVEL');bevel.width=.000045;bevel.segments=3
 o.modifiers.new('Normals','WEIGHTED_NORMAL');return o
# Photo-derived proportions, approximate dimensions, not a manufacturer footprint.
prism('Body',[(-.00325,-.0028),(.00325,-.0028),(.00325,.00235),(.0028,.0029),(-.0028,.0029),(-.00325,.00235)],.00030,.00245,bodymat)
prism('Metal_Tab',[(-.00275,-.0025),(.00275,-.0025),(.00275,.0039),(.00245,.00415),(-.00245,.00415),(-.00275,.0039)],.00010,.00048,steel)
def lead(name,x,long):
 # Extruded bent strip: downward shoulder then a flat solder foot.
 path=[(-.00265,.00105),(-.00325,.00105),(-.0038,.00028),(-.00565,.00028)] if long else [(-.00265,.00105),(-.0035,.00105)]
 w=.00075;t=.00024
 verts=[]
 for y,z in path:verts += [(x-w/2,y,z-t/2),(x+w/2,y,z-t/2),(x+w/2,y,z+t/2),(x-w/2,y,z+t/2)]
 faces=[(3,2,1,0),tuple(range(4*(len(path)-1),4*len(path)))]
 for j in range(len(path)-1):
  for k in range(4):faces.append((j*4+k,j*4+(k+1)%4,(j+1)*4+(k+1)%4,(j+1)*4+k))
 mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
 o=bpy.data.objects.new(name,mesh);scene.collection.objects.link(o);o.parent=root;o.data.materials.append(steel)
 b=o.modifiers.new('Rounded_edges','BEVEL');b.width=.00004;b.segments=3;o.modifiers.new('Normals','WEIGHTED_NORMAL')
lead('Lead_Left',-.0023,True);lead('Lead_Center_Short',0,False);lead('Lead_Right',.0023,True)
def text(name,value,size,y):
 c=bpy.data.curves.new(name,'FONT');c.body=value;c.align_x='CENTER';c.size=size;c.extrude=0
 o=bpy.data.objects.new(name,c);scene.collection.objects.link(o);o.parent=root;o.location=(0,y,.002451);o.data.materials.append(ink)
text('Marking_D4184','D4184',.00105,.0011)
text('Marking_PJ528','PJ528',.00085,-.00035)
bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.00046,depth=.000008,location=(0,-.0017,.002455))
o=bpy.context.object;o.name='Mold_Index_Dot';o.parent=root;o.data.materials.append(bodymat)
root['dimension_note']='Photo-derived approximate size; verify manufacturer drawing before physical use.'
root['reference']='User D4184 / PJ528 photo; pin functions not assigned.'
# Export the independent product only.
bpy.ops.object.select_all(action='DESELECT')
for o in [root]+list(root.children_recursive):o.select_set(True)
bpy.context.view_layer.objects.active=root
out=os.path.join(os.path.dirname(base),'Assets','MOSFETInspection','Models','MOSFET')
os.makedirs(out,exist_ok=True)
bpy.ops.export_scene.fbx(filepath=os.path.join(out,'MOSFET_D4184.fbx'),use_selection=True,object_types={'EMPTY','MESH','OTHER'},axis_forward='-Z',axis_up='Y',apply_unit_scale=True,bake_anim=False)
# Neutral studio preview; helpers kept outside product root.
floor=mat('Preview_White',(.65,.67,.69),0,.8)
bpy.ops.mesh.primitive_plane_add(size=.2);bpy.context.object.name='Preview_Floor';bpy.context.object.data.materials.append(floor)
world=bpy.data.worlds.new('Studio');scene.world=world;world.use_nodes=True;world.node_tree.nodes.get('Background').inputs[0].default_value=(.6,.6,.6,1)
for loc,power,size in [((-.01,-.005,.02),.012,.015),((.012,.01,.015),.009,.012)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.shape='DISK';l.data.size=size;l.rotation_euler=(Vector((0,0,0))-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(.006,-.009,.036));camera=bpy.context.object;camera.rotation_euler=(Vector((0,-.0007,.001))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=.014;camera.data.clip_start=.0001;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.samples=48
scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(base,'MOSFET_D4184_preview.png')
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':area.spaces.active.clip_start=.00001;area.spaces.active.region_3d.view_distance=.022;area.spaces.active.region_3d.view_location=(0,-.001,.001)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'MOSFET_D4184.blend'))
bpy.ops.render.render(write_still=True)
print('MOSFET_MODEL_OK')
