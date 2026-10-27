import bpy, math, os, json
from mathutils import Vector
base=os.path.dirname(__file__)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene;scene.unit_settings.system='METRIC'
def material(name,c,metal=0,rough=.35,transmission=0):
 m=bpy.data.materials.new(name);m.diffuse_color=(*c,1);m.use_nodes=True
 p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;p.inputs['Transmission Weight'].default_value=transmission;p.inputs['IOR'].default_value=1.46
 return m
amber=material('FOUP_Amber_Polymer',(.65,.24,.045),rough=.22,transmission=.58)
grey=material('FOUP_Door_Polymer',(.12,.15,.17),rough=.4)
dark=material('FOUP_Slot_Rails',(.055,.065,.07),rough=.5)
steel=material('FOUP_Coupling_Metal',(.6,.64,.67),metal=.75,rough=.25)
silicon=material('Wafer_Silicon',(.035,.10,.17),metal=.55,rough=.22)
root=bpy.data.objects.new('FOUP_300mm_Concept',None);scene.collection.objects.link(root)
def empty(name,p,parent=root):
 o=bpy.data.objects.new(name,None);scene.collection.objects.link(o);o.parent=parent;o.location=p;o.empty_display_size=.03;return o
def box(name,p,size,m,parent=root,bevel=.006):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=name;o.parent=parent;o.location=p;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if bevel:
  b=o.modifiers.new('Rounded_Moulding','BEVEL');b.width=bevel;b.segments=4;o.modifiers.new('Weighted_Normals','WEIGHTED_NORMAL')
 return o
shell=empty('FOUP_Shell',(0,0,0))
box('FOUP_Base',(0,0,.015),(.40,.38,.03),grey,shell)
box('FOUP_Back',(0,.184,.178),(.386,.012,.296),amber,shell)
for x in [-.194,.194]:box('FOUP_Side',(x,0,.178),(.012,.368,.296),amber,shell)
box('FOUP_Roof',(0,0,.331),(.40,.38,.018),amber,shell)
for x in [-.185,.185]:box('FOUP_Front_Jamb',(x,-.183,.18),(.018,.018,.302),grey,shell)
door=empty('FOUP_Door_ANIM',(0,-.199,.18))
box('FOUP_Door_Panel',(0,0,0),(.364,.025,.294),grey,door,.012)
box('FOUP_Door_Recess',(0,-.014,0),(.306,.007,.236),dark,door,.014)
for x in [-.10,.10]:
 bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.018,depth=.006,location=(0,0,0))
 o=bpy.context.object;o.name='FOUP_Door_Latch';o.parent=door;o.location=(x,-.020,-.08);o.rotation_euler.x=math.pi/2;o.data.materials.append(steel)
 box('FOUP_Door_Latch_Slot',(x,-.024,-.08),(.022,.002,.004),dark,door,.001)
flange=empty('FOUP_Top_Flange',(0,0,.34))
box('FOUP_Handle_Pedestal',(0,0,.012),(.10,.08,.024),grey,flange)
box('FOUP_OHT_Grip_Flange',(0,0,.035),(.16,.13,.022),grey,flange)
empty('OHT_Grip_Anchor',(0,0,.386))
empty('LoadPort_Dock_Anchor',(0,0,0))
for x,y in [(-.13,-.11),(.13,-.11),(0,.12)]:
 bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.018,depth=.008)
 o=bpy.context.object;o.name='FOUP_Docking_Pad';o.parent=root;o.location=(x,y,.004);o.data.materials.append(steel)
slots=empty('FOUP_Slot_Rack',(0,0,0));wafers=empty('FOUP_Wafers',(0,0,0))
for x in [-.175,.175]:box('FOUP_Rack_Spine',(x,.025,.166),(.012,.25,.27),dark,slots,.003)
for i in range(25):
 z=.055+i*.009
 for x in [-.15,.15]:box('Slot_%02d_Support'% (i+1),(x,.025,z-.002),(.035,.20,.003),dark,slots,.001)
 verts=[]
 for zz in [z,z+.0008]:
  for j in range(128):
   angle=2*math.pi*j/128;r=.15
   if abs(angle-1.5*math.pi)<.05:r-=.003
   verts.append((r*math.cos(angle),.015+r*math.sin(angle),zz))
 faces=[tuple(reversed(range(128))),tuple(range(128,256))]+[(j,(j+1)%128,(j+1)%128+128,j+128) for j in range(128)]
 mesh=bpy.data.meshes.new('Wafer_%02d'% (i+1));mesh.from_pydata(verts,[],faces);mesh.update()
 o=bpy.data.objects.new(mesh.name,mesh);scene.collection.objects.link(o);o.parent=wafers;o.data.materials.append(silicon)
empty('Wafer_Pick_Anchor',(0,.015,.0558))
root['design_note']='Concept FOUP for OHT visualization. 300mm wafer disks; case and interfaces approximate, not SEMI-certified dimensions.'
root['animation_parts']='FOUP_Door_ANIM, FOUP_Top_Flange, FOUP_Wafers/Wafer_01..25; anchors for OHT and loadport.'
out=os.path.join(os.path.dirname(base),'Assets','MOSFETInspection','Models','OHT');os.makedirs(out,exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for o in [root]+list(root.children_recursive):o.select_set(True)
bpy.context.view_layer.objects.active=root
bpy.ops.export_scene.fbx(filepath=os.path.join(out,'FOUP_300mm_Concept.fbx'),use_selection=True,object_types={'EMPTY','MESH'},axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False)
with open(os.path.join(out,'FOUP_design.json'),'w') as f:json.dump({'wafer_count':25,'wafer_diameter_m':.30,'case_dimensions_m':[.40,.38,.386],'note':root['design_note']},f,indent=2)
# Preview opens the door to reveal the rack. Export remains assembled.
door.location.x=-.46;door.location.y=-.28;door.rotation_euler.z=math.radians(-12)
scene.world.color=(.45,.45,.45)
floor=material('Preview_White',(.72,.74,.76),rough=.7)
bpy.ops.mesh.primitive_plane_add(size=20);bpy.context.object.name='Preview_Floor';bpy.context.object.location.z=-.002;bpy.context.object.data.materials.append(floor)
for p,power,size in [((1,-1,2),180,1.5),((-1,-.5,1),110,1),((0,1,1.5),150,1)]:
 bpy.ops.object.light_add(type='AREA',location=p);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,.18))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(.8,-1.25,.85));camera=bpy.context.object;camera.rotation_euler=(Vector((-.12,0,.18))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=1.35;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.render.resolution_x=1100;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(base,'FOUP_300mm_preview.png')
# Save assembled, render with the detached door for visibility.
door.location=(0,-.199,.18);door.rotation_euler.z=0
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'FOUP_300mm_Concept.blend'))
restyle=os.path.join(base,'restyle_existing_foup.py')
exec(compile(open(restyle,encoding='utf-8').read(),restyle,'exec'),{'__file__':restyle})
door.location.x=-.46;door.location.y=-.28;door.rotation_euler.z=math.radians(-12)
bpy.ops.render.render(write_still=True)
print('FOUP_MODEL_OK: 25 separate wafers, removable door, top grip anchor, dock anchor')
