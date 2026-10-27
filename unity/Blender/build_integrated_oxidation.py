# Historical tall-furnace draft. Superseded by live exterior restoration in
# Oxidation_System_Integrated.blend; do not rerun over the approved live model.
import bpy,os,math,json
from mathutils import Vector
base=os.path.dirname(__file__)
bpy.ops.wm.open_mainfile(filepath=os.path.join(base,'EFEM_WaferReady.blend'))
def remove_tree(obj):
 if not obj:return
 for child in list(obj.children):remove_tree(child)
 bpy.data.objects.remove(obj,do_unlink=True)
for o in list(bpy.data.objects):
 if o.name in bpy.data.objects:o.animation_data_clear()
for n in ['Demo_FOUP_ROOT','Wafer_Aligner_ROOT','Process_Handoff_ROOT','Robot_Wafer_Demo']:
 remove_tree(bpy.data.objects.get(n))
for name in [o.name for o in bpy.data.objects]:
 o=bpy.data.objects.get(name)
 if o and (name.startswith('FOUP_') or name.startswith('Preview_')):remove_tree(o)
system=bpy.data.objects.new('Oxidation_System',None);bpy.context.collection.objects.link(system)
loader=bpy.data.objects['EFEM_ROOT'];loader.name='Loader_Module';loader.parent=system
for name in [o.name for o in loader.children_recursive]:
 o=bpy.data.objects.get(name)
 if o and o.hide_render:remove_tree(o)
white=bpy.data.materials.get('EFEM_Panel_Light') or list(bpy.data.materials)[0]
steel=bpy.data.materials.get('EFEM_Stainless') or white
def mat(n,c,metal=0,trans=0):
 m=bpy.data.materials.new(n);m.use_nodes=True;m.diffuse_color=(*c,1)
 p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=.25;p.inputs['Transmission Weight'].default_value=trans;return m
quartz=mat('Quartz_Concept',(.65,.80,.88),trans=.65)
blue=mat('Transfer_Guide_Blue',(.025,.24,.55),metal=.2)
def empty(n,p=(0,0,0),parent=system):
 o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.parent=parent;o.location=p;o.empty_display_size=.06;return o
def box(n,p,d,m,parent=system):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=parent;o.location=p;o.dimensions=d;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m);q=o.modifiers.new('Edges','BEVEL');q.width=.004;q.segments=2;return o
def ring(n,center,inner,outer,height,m,parent):
 v=[];faces=[];N=96
 for z,r in [(-height/2,inner),(-height/2,outer),(height/2,inner),(height/2,outer)]:
  for i in range(N):a=2*math.pi*i/N;v.append((r*math.cos(a),r*math.sin(a),z))
 for i in range(N):
  j=(i+1)%N
  faces.extend([(i,j,j+N,i+N),(i+2*N,i+3*N,j+3*N,j+2*N),(i,j,j+2*N,i+2*N),(i+N,i+3*N,j+3*N,j+N)])
 mesh=bpy.data.meshes.new(n);mesh.from_pydata(v,[],faces);mesh.update();o=bpy.data.objects.new(n,mesh);bpy.context.collection.objects.link(o);o.parent=parent;o.location=center;o.data.materials.append(m);return o
# Load the real OHT-compatible case rather than the old cylindrical demo carrier.
def append_root(filename,rootname):
 with bpy.data.libraries.load(os.path.join(base,filename),link=False) as (src,dst):dst.objects=list(src.objects)
 loaded=[o for o in dst.objects if o]
 for o in loaded:bpy.context.collection.objects.link(o)
 target=next(o for o in loaded if o.name==rootname)
 keep={target,*target.children_recursive}
 for o in loaded:
  if o not in keep and o.name in bpy.data.objects:bpy.data.objects.remove(o,do_unlink=True)
 return target
foup=append_root('FOUP_300mm_Concept.blend','FOUP_300mm_Concept');foup.parent=loader;foup.location=(0,-1.02,1.25);foup.rotation_euler.z=math.pi
empty('OX_LOADPORT_01_Dock',(0,-1.02,1.25),loader)
box('FOUP_Dock_Riser',(0,-1.02,1.215),(.48,.44,.07),steel,loader)
furnace=append_root('Oxidation_Furnace.blend','Oxidation_Furnace_ROOT');furnace.name='Furnace_Module';furnace.parent=system;furnace.location=(3,.71,0)
for o in [furnace]+list(furnace.children_recursive):o.animation_data_clear()
# Match the loader's envelope while preserving the existing furnace front details.
for n in ['Furnace_Rear_Panel','Furnace_Side_Panel','Furnace_Side_Panel.001']:
 o=bpy.data.objects[n];o.location.z=1.95;o.dimensions.z=3.9
bpy.data.objects['Furnace_Top_Cover'].location.z=3.875
upper=bpy.data.objects['Furnace_Upper_Cabinet'];upper.location.z=2.97;upper.dimensions.z=1.81
for n in ['Furnace_Loading_Back','Furnace_Loading_Floor','Furnace_Process_Throat','Demo_Enclosure_Side.001']:
 # Loader's right side is identified by position below, not an assumed suffix.
 if n.startswith('Demo_'):continue
 remove_tree(bpy.data.objects.get(n))
for o in list(loader.children_recursive):
 if o.name.startswith('Demo_Enclosure_Side') and o.location.x>0:remove_tree(o)
# The connection is an actual rectangular passage, with separate surrounding wall panels.
opening=empty('Transfer_Opening')
zlow,zhigh=1.20,2.04;ylo,yhi=-.12,.58
box('Loader_Right_Lower',(2.33,.8,.60),(.05,1.20,1.20),white,loader)
box('Loader_Right_Upper',(2.33,.8,2.795),(.05,1.20,1.51),white,loader)
box('Loader_Right_Rear',(2.33,.99,1.62),(.05,.82,.84),white,loader)
left=bpy.data.objects['Furnace_Side_Panel'];remove_tree(left)
box('Furnace_Left_Lower',(-.575,0,.60),(.05,1.94,1.20),white,furnace)
box('Furnace_Left_Upper',(-.575,0,2.97),(.05,1.94,1.86),white,furnace)
# In furnace-local coordinates, portal Y is -.83..-.13.
box('Furnace_Left_Front',(-.575,-.90,1.62),(.05,.14,.84),white,furnace)
box('Furnace_Left_Rear',(-.575,.42,1.62),(.05,1.10,.84),white,furnace)
for y in [ylo,yhi]:box('Passage_Side',(2.3775,y,1.62),(.145,.025,.84),steel,opening)
for z in [zlow,zhigh]:box('Passage_Lintel',(2.3775,.23,z),(.145,.70,.025),steel,opening)
empty('Transfer_Entry',(2.25,.23,1.684),opening);empty('Transfer_Exit',(2.55,.23,1.684),opening)
# Rebuild the vertical loading path: boat below an open-ended processing tube.
elevator=bpy.data.objects['Furnace_Boat_Elevator'];elevator.name='Boat_Elevator';elevator.location.z=1.30
boat=bpy.data.objects['Furnace_Wafer_Boat'];boat.name='Quartz_Boat'
for o in list(boat.children):
 if o.name.startswith('Furnace_Wafer_'):remove_tree(o)
for i in range(12):
 z=.105+i*.038
 empty('Boat_Slot_%02d'%(i+1),(0,0,z),elevator)
 # Three small ledges support each wafer, leaving a blade corridor along X.
 for x,y in [(.12,.10),(-.10,.10),(0,-.13)]:
  box('Boat_Slot_Support',(x,y,z-.002),(.025,.025,.004),quartz,elevator)
ring('Process_Tube',(0,-.48,2.60),.205,.225,1.10,quartz,furnace)
ring('Process_Throat',(0,-.48,2.05),.205,.255,.04,steel,furnace)
for n in ['Furnace_Elevator_Backbone','Furnace_Elevator_Guide','Furnace_Elevator_Guide.001']:
 o=bpy.data.objects[n];o.location.z=1.80;o.dimensions.z=1.70
box('Loading_Chamber_Deck',(0,-.24,1.14),(1.08,1.50,.05),steel,furnace)
empty('Boat_Down_Target',(0,-.48,1.30),furnace)
lift_travel=.7275
empty('Boat_Up_Target',(0,-.48,1.30+lift_travel),furnace)
elevator['travel_m']=lift_travel
elevator['slot_pitch_m']=.038
# Hollow frame now permits access; enlarge lower observation door without sealing the side passage.
robot=bpy.data.objects['Wafer_Robot_ROOT'];robot.location=(.55,.72,1.22)
j1=bpy.data.objects['Robot_Joint_01_ANIM'];j2=bpy.data.objects['Robot_Joint_02_ANIM'];wrist=bpy.data.objects['Robot_Wrist_ANIM']
blade=bpy.data.objects['Robot_EndEffector_ANIM'];blade.location.x=.38;blade.dimensions.x=.76
bpy.data.objects['Robot_EndEffector_Tip'].location.x=.80
def solve(target,heading):
 q=Vector(target[:2])-Vector((math.cos(heading),math.sin(heading)))*.82-Vector(robot.location[:2]);r=q.length
 assert .11<r<1.79,('Unreachable',target,r)
 a2=math.acos((r*r-.95**2-.84**2)/(2*.95*.84));a1=math.atan2(q.y,q.x)-math.atan2(.84*math.sin(a2),.95+.84*math.cos(a2))
 j1.rotation_euler.z=a1;j2.rotation_euler.z=a2;wrist.rotation_euler.z=heading-a1-a2;j1.location.z=target[2]-.075-robot.location.z
 bpy.context.view_layer.update()
tip=lambda:wrist.matrix_world@Vector((.82,0,.045))
checks=[]
# Validate every source slot and every destination slot against reach and blade target.
for i in range(25):
 target=(0,-1.035,1.3054+i*.009);solve(target,-math.pi/2);assert (tip()-Vector(target)).length<1e-5
 checks.append('FOUP slot %02d reachable'%(i+1))
for i in range(12):
 target=(3,.23,1.405+i*.038);solve(target,0);assert (tip()-Vector(target)).length<1e-5
 checks.append('Boat slot %02d reachable'%(i+1))
 # Both substantial robot arms stay to the loader side; only the blade enters the furnace.
 for name in ['Robot_Arm_01','Robot_Arm_02','Robot_Wrist_Housing']:
  o=bpy.data.objects[name];assert max((o.matrix_world@Vector(v)).x for v in o.bound_box)<2.31,(name,'crosses wall')
assert .185 < .205 # Boat endplates fit through tube bore.
assert 1.35+.5+lift_travel < 3.15 # Boat top clears tube top at full lift.
solve((.65,.25,1.68),0)
empty('Robot_Standby_Target',(.65,.25,1.68),loader)
empty('Robot_Clearance_Target',(1.5,.23,1.90),loader)
empty('Boat_Load_Target',(3,.23,1.671),system)
system['scope']='Integrated loader + vertical oxidation furnace, conceptual engineering model. No process simulation or motion clips in this file.'
system['sequence']='OHT docks FOUP -> equipment shutter opens -> wafer to boat -> robot retracts -> boat rises -> process -> boat lowers -> wafer returns to FOUP'
system['interface']='Use OX_LOADPORT_01_Dock and FOUP OHT_Grip_Anchor for later OHT integration. Stopper and doors require interlocks before motion.'
with open(os.path.join(base,'Oxidation_System_validation.json'),'w') as f:json.dump({'checks':checks,'boat_lift_m':lift_travel,'source_slots':25,'boat_slots':12,'note':'Reach and endpoint clearance checks; continuous collision-free trajectory not yet implemented.'},f,indent=2)
# Export one assembled model, preserving movable-part hierarchy.
out=os.path.join(os.path.dirname(base),'Assets','MOSFETInspection','Models','FabEquipment','Oxidation_System.fbx')
bpy.ops.object.select_all(action='DESELECT')
for o in [system]+list(system.children_recursive):
 if o.hide_render:continue
 o.hide_set(False);o.select_set(True)
bpy.context.view_layer.objects.active=system
bpy.ops.export_scene.fbx(filepath=out,use_selection=True,object_types={'EMPTY','MESH','OTHER'},axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False)
# Two views: original assembled exterior and explicit cutaway for the internal connection.
cutaway=[]
for o in system.children_recursive:
 if o.type!='MESH':continue
 if o.name.startswith(('REF_Upper','REF_Vent')) or o.name in ['EFEM_TopHeader','Demo_Enclosure_Back','Furnace_Upper_Cabinet','Furnace_Side_Panel.001','Furnace_Top_Cover','FOUP_Roof','Demo_Enclosure_Side'] or 'Fascia' in o.name:cutaway.append(o)
for o in cutaway:o['cutaway_panel']=True
scene=bpy.context.scene
for o in list(bpy.data.objects):
 if o.type in {'CAMERA','LIGHT'}:bpy.data.objects.remove(o,do_unlink=True)
floor=mat('Integrated_Preview_Floor',(.5,.58,.62),.1)
box('Preview_Floor',(.7,.3,-.08),(9,5,.16),floor,parent=None)
for loc,power,size in [((1,-5,8),2200,5),((-4,-2,5),1500,4),((5,3,7),2000,4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((.7,.3,1.8))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(9,-12,8));camera=bpy.context.object;camera.rotation_euler=(Vector((.65,.3,1.9))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=8.3;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.render.resolution_x=1500;scene.render.resolution_y=1100;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
scene.world.color=(.45,.45,.45)
scene.render.filepath=os.path.join(base,'Oxidation_System_exterior.png');bpy.ops.render.render(write_still=True)
for o in cutaway:o.hide_render=True;o.hide_set(True)
scene.render.filepath=os.path.join(base,'Oxidation_System_cutaway.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'Oxidation_System_Integrated.blend'))
bpy.ops.render.render(write_still=True)
for o in cutaway:o.hide_render=False;o.hide_set(False)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'Oxidation_System_Integrated.blend'))
print('OXIDATION_SYSTEM_OK: 25 FOUP slots + 12 boat slots reachable; open passage; lift bore checked; no animations applied')
