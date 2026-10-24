import bpy, math, os, json
from mathutils import Vector
base=os.path.dirname(__file__)
bpy.ops.wm.open_mainfile(filepath=os.path.join(base,'EFEM.blend'))
root=bpy.data.objects['EFEM_ROOT']
for o in bpy.data.objects:
 o.animation_data_clear()
 if o.name.startswith('FOUP_') or o.name=='Aligner_Wafer_Demo':o.hide_render=True;o.hide_set(True)
def box(name,p,d,mat,parent=root):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=name;o.parent=parent;o.location=p;o.dimensions=d;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 o.data.materials.append(mat);b=o.modifiers.new('Rounded_edges','BEVEL');b.width=.008;b.segments=2;return o
steel=bpy.data.materials.get('EFEM_Stainless') or list(bpy.data.materials)[0]
white=bpy.data.materials.get('EFEM_Panel_Light') or steel
# Hollow rear enclosure instead of the former solid cabinet around the robot.
solid=bpy.data.objects.get('EFEM_RearCabinet')
if solid:bpy.data.objects.remove(solid,do_unlink=True)
box('Demo_Enclosure_Back',(0,1.40,1.88),(4.70,.05,3.35),white)
for x in [-2.33,2.33]:box('Demo_Enclosure_Side',(x,.80,1.88),(.05,1.20,3.35),white)
amber=bpy.data.materials.new('Demo_FOUP_Amber');amber.use_nodes=True
p=next(n for n in amber.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(.55,.2,.025,1);p.inputs['Roughness'].default_value=.3
foup=bpy.data.objects.new('Demo_FOUP_ROOT',None);bpy.context.collection.objects.link(foup);foup.parent=root;foup.location=(0,-1.02,0)
# Cylindrical demonstration carrier, rear aperture faces the loadport.
for name,z in [('Demo_FOUP_Base',1.23),('Demo_FOUP_Roof',2.04)]:
 bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=.39,depth=.045)
 o=bpy.context.object;o.name=name;o.parent=foup;o.location=(0,0,z);o.data.materials.append(steel if z<1.5 else amber)
verts=[];faces=[]
for i in range(65):
 a=math.radians(140+260*i/64)
 for r,z in [(.39,1.25),(.39,2.02),(.365,1.25),(.365,2.02)]:verts.append((r*math.cos(a),r*math.sin(a),z))
for i in range(64):
 a=i*4;b=(i+1)*4
 faces.extend([(a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a+1,b+1,b+3,a+3),(a,a+2,b+2,b)])
faces.extend([(0,1,3,2),(256,258,259,257)])
mesh=bpy.data.meshes.new('Carrier_CylindricalShell');mesh.from_pydata(verts,[],faces);mesh.update()
o=bpy.data.objects.new('Demo_FOUP_CylindricalShell',mesh);bpy.context.collection.objects.link(o);o.parent=foup;o.data.materials.append(amber)
# The old door frame was a solid cube. Replace it with a genuine opening.
for name in ['REF_LP2_DoorFrame','REF_LP2_Header','REF_LP2_Label']:
 o=bpy.data.objects.get(name)
 if o:bpy.data.objects.remove(o,do_unlink=True)
for x in [-.43,.43]:box('Demo_Port_FrameSide',(x,-.50,1.64),(.06,.10,.88),steel)
for z in [1.20,2.08]:box('Demo_Port_FrameCross',(0,-.50,z),(.92,.10,.06),steel)
port=bpy.data.objects['REF_LP2_Door_ANIM']
port.location=(0,-.555,1.64);port.dimensions=(.80,.055,.80)
# Carrier remains intact; the equipment shutter is the moving gate.
wafer=bpy.data.objects['Robot_Wafer_Demo'];wafer.parent=root;wafer.hide_set(False);wafer.hide_render=False
j1=bpy.data.objects['Robot_Joint_01_ANIM'];j2=bpy.data.objects['Robot_Joint_02_ANIM'];wrist=bpy.data.objects['Robot_Wrist_ANIM']
robot=bpy.data.objects['Wafer_Robot_ROOT'];robot.location.y=.72
# Support wafer on pins so the blade can lower and withdraw without crossing a solid chuck.
chuck=bpy.data.objects['Aligner_Chuck_ANIM'];chuck.location.z=.21;chuck.dimensions.z=.04
alignroot=bpy.data.objects['Wafer_Aligner_ROOT']
for dx,dy in [(-.10,.10),(.10,.10),(0,-.12)]:
 bpy.ops.mesh.primitive_cylinder_add(vertices=20,radius=.015,depth=.114)
 pin=bpy.context.object;pin.name='Demo_Aligner_SupportPin';pin.parent=alignroot;pin.location=(dx,dy,.287);pin.data.materials.append(steel)
basepos=Vector((robot.location.x,robot.location.y))
L1=.95;L2=.84;tip=.78
def solve(target,heading):
 wristxy=Vector(target[:2])-Vector((math.cos(heading),math.sin(heading)))*tip
 delta=wristxy-basepos;wr=delta.length;angle=math.atan2(delta.y,delta.x)
 assert abs(L1-L2)<wr<L1+L2,('Unreachable wafer target',target,wr)
 q2=math.acos((wr*wr-L1*L1-L2*L2)/(2*L1*L2));q1=angle-math.atan2(L2*math.sin(q2),L1+L2*math.cos(q2))
 return q1,q2,heading-q1-q2,target[2]-.075-robot.location.z
pick=(0,-1.02,1.685);align=(1.42,.23,1.56);clear=(0,.12,1.73);home=(.55,.25,1.82)
# Each entry: frame, arm target, wafer position, docking Y, door drop.
ready=(0,.12,1.685)
poses=[(1,ready,(0,-1.47,1.685),-.45,0),(35,ready,pick,0,0),(65,ready,pick,0,-1.05),
 (100,pick,pick,0,-1.05),(120,(0,-1.02,1.73),(0,-1.02,1.73),0,-1.05),
 (160,clear,clear,0,-1.05),(205,(1.42,.23,1.73),(1.42,.23,1.73),0,-1.05),
 (230,align,align,0,-1.05),(250,(1.42,.23,1.53),align,0,-1.05),
 (280,(.55,.25,1.53),align,0,-1.05),(310,home,align,0,-1.05),(350,home,align,0,0)]
baked=[]
for frame in range(1,351):
 a,b=next(((a,b) for a,b in zip(poses,poses[1:]) if a[0]<=frame<=b[0]))
 f=(frame-a[0])/(b[0]-a[0])
 target=tuple(Vector(a[1]).lerp(Vector(b[1]),f));wp=tuple(Vector(a[2]).lerp(Vector(b[2]),f))
 heading=-math.pi/2 if frame<=160 else (-math.pi/2)*(1-min(1,(frame-160)/45))
 baked.append((frame,target,wp,a[3]+(b[3]-a[3])*f,a[4]+(b[4]-a[4])*f,heading))
for frame,target,wp,dock,drop,heading in baked:
 q1,q2,qw,z=solve(target,heading);j1.rotation_euler.z=q1;j2.rotation_euler.z=q2;wrist.rotation_euler.z=qw;j1.location.z=z
 for o in [j1,j2,wrist]:o.keyframe_insert(data_path='rotation_euler',frame=frame);o.keyframe_insert(data_path='location',frame=frame)
 foup.location.y=-1.02+dock;foup.keyframe_insert(data_path='location',frame=frame)
 port.location.z=1.64+drop;port.keyframe_insert(data_path='location',frame=frame)
 wafer.location=wp;wafer.keyframe_insert(data_path='location',frame=frame)
# Verify pickup and placement pivots, using evaluated meshes rather than names alone.
scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=350;scene.render.fps=30
for frame in range(1,351):
 scene.frame_set(frame);bpy.context.view_layer.update()
 # Entire upper/lower arm envelopes must stay on the EFEM side of the opening.
 for name in ['Robot_Arm_01','Robot_Arm_02','Robot_Joint_01_Housing','Robot_Joint_02_Housing','Robot_Wrist_Housing']:
  arm=bpy.data.objects[name];min_y=min((arm.matrix_world@Vector(v)).y for v in arm.bound_box)
  assert min_y>-.445,(frame,'Arm crosses port plane',name,min_y)
 if frame<100 or frame>230:continue
 expected=wrist.matrix_world@Vector((.78,0,.045))
 assert (expected-wafer.matrix_world.translation).length<.0001,(frame,expected,wafer.matrix_world.translation)
scene.frame_set(1)
root['demo_note']='Cylindrical demonstration carrier; equipment gate lowers. Upper arms remain behind port plane. Simplified carrier, not a commercial FOUP replica.'
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'EFEM_WaferReady.blend'))
bpy.ops.object.select_all(action='DESELECT')
for o in [root]+list(root.children_recursive):
 if o.hide_render or o.name.startswith('FOUP_') or o.name=='Aligner_Wafer_Demo' or o.name.startswith('Preview_'):continue
 o.hide_set(False);o.select_set(True)
bpy.context.view_layer.objects.active=root
out=os.path.join(os.path.dirname(base),'Assets','MOSFETInspection','Models','FabEquipment','EFEM_WaferDemo.fbx')
bpy.ops.export_scene.fbx(filepath=out,use_selection=True,object_types={'EMPTY','MESH','OTHER'},axis_forward='-Z',axis_up='Y',bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_force_startend_keying=True,bake_anim_step=1,bake_anim_simplify_factor=0,add_leaf_bones=False)
print('EFEM_READY_OK pickup/place checks passed; 350 frames; separate FBX and blend saved')
