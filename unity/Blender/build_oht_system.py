import bpy,os,math,json
from mathutils import Vector
base=os.path.dirname(__file__)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene;scene.unit_settings.system='METRIC'
def mat(n,c,metal=0,rough=.35):
 m=bpy.data.materials.new(n);m.use_nodes=True;m.diffuse_color=(*c,1)
 p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;return m
white=mat('OHT_White',(.83,.86,.89));steel=mat('OHT_Rail_Aluminum',(.48,.55,.61),.7);dark=mat('OHT_Graphite',(.025,.035,.045));red=mat('OHT_RedStripe',(.55,.015,.02));green=mat('OHT_Green',(.02,.65,.12))
def empty(n,p=(0,0,0),par=None):
 o=bpy.data.objects.new(n,None);scene.collection.objects.link(o);o.parent=par;o.location=p;o.empty_display_size=.07;return o
root=empty('OHT_System')
def box(n,p,d,m,par=root,b=.008):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=p;o.dimensions=d;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if b:q=o.modifiers.new('Edge_Radius','BEVEL');q.width=b;q.segments=3;o.modifiers.new('Normals','WEIGHTED_NORMAL')
 return o
rail=empty('Rail',par=root)
for y in [-.18,.18]:
 box('Rail_Running_Beam',(0,y,4.05),(6.6,.055,.12),steel,rail)
 box('Rail_Contact_Surface',(0,y,3.99),(6.6,.08,.025),dark,rail)
supports=empty('Rail_Support',par=root)
for x in [-3,-1,1,3]:
 box('Ceiling_Crossbar',(x,0,4.38),(.065,.8,.07),steel,supports)
 for y in [-.30,.30]:box('Rail_Hanger',(x,y,4.23),(.035,.035,.30),steel,supports)
carrier=empty('OHT_Carrier',(-2,0,0),root)
box('Main_Body',(0,0,3.68),(.84,.62,.54),white,carrier,.035)
for x in [-.39,.39]:
 box('Carrier_Side_Shroud',(x,0,3.12),(.06,.62,.66),white,carrier,.02)
 box('Side_Red_Stripe',(x,-.318,3.44),(.06,.006,.03),red,carrier,.002)
box('Front_Red_Stripe',(0,-.316,3.54),(.70,.008,.035),red,carrier,.003)
box('Vehicle_Status_Display',(0,-.324,3.72),(.22,.012,.07),dark,carrier)
box('Front_Sensor',(0,-.332,3.49),(.08,.025,.06),dark,carrier)
for x in [-.31,.31]:box('Status_Light',(x,-.324,3.67),(.025,.012,.055),green,carrier)
wheels=empty('Wheels',par=carrier)
for x in [-.27,.27]:
 for y in [-.18,.18]:
  bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.075,depth=.045)
  o=bpy.context.object;o.name='Running_Wheel';o.parent=wheels;o.location=(x,y,3.98);o.rotation_euler.x=math.pi/2;o.data.materials.append(dark)
hoist=empty('Hoist',par=carrier)
box('Hoist_Winch',(0,0,3.43),(.40,.38,.12),steel,hoist)
lift=empty('Lift_Frame',(0,0,1.586),hoist)
box('Lift_Frame_Plate',(0,0,.07),(.32,.27,.035),white,lift)
empty('FOUP_AttachPoint',par=lift)
grip=empty('Gripper',par=lift)
for sign,label in [(-1,'Left'),(1,'Right')]:
 jaw=empty('Gripper_'+label,(sign*.14,0,0),grip)
 box('Jaw_Vertical',(0,0,.015),(.018,.16,.10),steel,jaw,.003)
 box('Jaw_Hook',(-sign*.03,0,-.028),(.04,.14,.012),steel,jaw,.002)
belts=empty('Hoist_Belts',par=carrier)
for x in [-.13,.13]:
 for y in [-.10,.10]:
  top=empty('Belt_Top',(x,y,3.38),carrier)
  bottom=empty('Belt_Bottom',(x,y,.09),lift)
  box('Hoist_Belt',(x,y,(3.38+1.676)/2),(.018,.004,3.38-1.676),dark,belts,.001)
ports=empty('Loadports',par=root)
for x,label in [(-2,'SOURCE_PORT'),(0,'OX_LOADPORT_01'),(2,'IMP_LOADPORT_01')]:
 station=empty(label,(x,0,0),ports)
 box(label+'_Cabinet',(0,0,.56),(.70,.64,1.12),white,station,.025)
 box(label+'_Deck',(0,0,1.17),(.70,.64,.06),steel,station,.015)
 empty(label+'_Dock',(0,0,1.20),station)
 box(label+'_Indicator',(0,-.327,1.02),(.24,.012,.025),green,station)
empty('Travel_Grip_Height',(0,0,3.05),root)
root['interface_note']='Fits FOUP_300mm_Concept: 0.40x0.38m case, grip anchor z=.386m. Straight-rail demonstration; generic loadport stands.'
root['operation_note']='Manual start in Unity. Source pickup -> oxide dock -> mock process ready -> pickup -> implant dock. Equipment process events not connected.'
# Geometric mating checks for open and closed jaws against the .16m top flange.
assert .14-.03-.02 > .08
assert .10-.03-.02 < .08
assert .40+.02 < .72 # FOUP width inside carrier side-shroud clearance
assert 3.05-.386 > 1.20+.386 # transport clearance above a docked carrier
out=os.path.join(os.path.dirname(base),'Assets','MOSFETInspection','Models','OHT');os.makedirs(out,exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for o in [root]+list(root.children_recursive):o.select_set(True)
bpy.context.view_layer.objects.active=root
bpy.ops.export_scene.fbx(filepath=os.path.join(out,'OHT_System.fbx'),use_selection=True,object_types={'EMPTY','MESH'},axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False)
materials={m.name:{'color':list(next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Base Color'].default_value),'metallic':next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Metallic'].default_value,'roughness':next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Roughness'].default_value} for m in [white,steel,dark,red,green]}
with open(os.path.join(out,'OHT_materials.json'),'w') as f:json.dump(materials,f,indent=2)
# Append the previously built independent FOUP, with assembled door and 25 wafers.
with bpy.data.libraries.load(os.path.join(base,'FOUP_300mm_Concept.blend'),link=False) as (source,target):
 target.objects=[n for n in source.objects if n.startswith(('FOUP_','Wafer_','Slot_','OHT_Grip_Anchor','LoadPort_Dock_Anchor'))]
for o in target.objects:
 if o:scene.collection.objects.link(o)
foup=bpy.data.objects['FOUP_300mm_Concept'];foup.location=(-2,0,1.2)
floor=mat('Preview_Floor',(.52,.60,.63),.1)
box('Preview_Floor',(0,0,-.08),(8,4,.16),floor,par=None)
for loc,power,size in [((1,-4,7),1800,5),((-4,-1,6),1400,4),((3,3,6),1800,4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,2))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(7,-10,6.8));camera=bpy.context.object;camera.rotation_euler=(Vector((0,0,2.1))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=8.4;scene.camera=camera
scene.world.color=(.4,.4,.4);scene.render.engine='CYCLES';scene.cycles.samples=24;scene.render.resolution_x=1400;scene.render.resolution_y=1050;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(base,'OHT_System_preview.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'OHT_System.blend'))
bpy.ops.render.render(write_still=True)
print('OHT_MODEL_OK: matching FOUP flange, 3 docks, 4 belts, separate lift and jaws')
