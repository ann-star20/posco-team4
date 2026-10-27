import bpy, math, os
from mathutils import Vector
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
base=os.path.dirname(__file__)
def mat(n,c,metal=0,alpha=1):
 m=bpy.data.materials.new(n);m.use_nodes=True
 p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,alpha);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=.27;p.inputs['Alpha'].default_value=alpha
 if alpha<1:m.surface_render_method='DITHERED'
 return m
white=mat('Clean_White',(.83,.86,.88),.1);dark=mat('Graphite',(.025,.035,.045),.3);steel=mat('Steel',(.40,.46,.50),.8);blue=mat('Header_Blue',(.13,.40,.64));amber=mat('FOUP_Amber',(.55,.13,.012),.1,.64);red=mat('Red',(.8,.025,.01));green=mat('Green',(.02,.65,.12));yellow=mat('Yellow',(.95,.65,.02));glass=mat('Dark_Window',(.025,.07,.10),.3)
def empty(n,loc=(0,0,0),par=None):
 o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.parent=par;o.location=loc;return o
root=empty('Ion_Implanter')
def box(n,loc,dims,m,par=root,b=.015):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if b:q=o.modifiers.new('Rounded_Edges','BEVEL');q.width=b;q.segments=3
 return o
def cyl(n,loc,r,d,m,par=root,front=False):
 bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=r,depth=d);o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.data.materials.append(m)
 if front:o.rotation_euler.x=math.pi/2
 return o
body=empty('Main_Body',par=root)
box('Front_Upper_Cabinet',(-.6,0,2.30),(3.75,1.2,1.05),white,body)
box('Front_Rear_Panel',(-.6,.57,1.30),(3.75,.07,2.5),white,body)
box('Front_Header',(-.6,-.615,2.70),(3.73,.03,.22),blue,body)
for x in (-1.65,-.15):box('Observation_Window',(x,-.62,2.02),(1.10,.025,.22),glass,body)
beam=empty('Beamline_Housing',par=root)
box('Rear_Tall_Housing',(.30,2.65,1.85),(3.85,3.5,3.7),white,beam)
box('Rear_Header',(.30,.88,3.54),(3.83,.03,.23),blue,beam)
for y in (1.2,2.1,3.0,3.9):
 box('Rear_Service_Seam',(2.235,y,1.84),(.012,.018,3.45),steel,beam)
 box('Rear_Service_Handle',(2.25,y+.25,1.8),(.025,.035,.25),dark,beam)
box('Beamline_Link',(-.2,.85,1.4),(2.6,1.4,2.4),white,beam)
for i,x in enumerate((-2.0,-1.05,-.10,.85),1):
 port=empty(f'Load_Port_{i:02d}',(x,-.87,0),root)
 box('Port_Body',(0,0,.61),(.86,.85,1.16),white,port)
 box('Port_Tray',(0,-.13,1.24),(.91,1.0,.12),white,port)
 box('Port_Door_Frame',(0,.28,1.65),(.84,.10,.75),white,port)
 box('Port_Door',(0,.21,1.62),(.68,.04,.55),steel,port)
 for j in range(6):box('Port_Status_LED',(-.24+j*.095,.20,2.0),(.05,.015,.022),green if j%2 else yellow,port,.002)
 f=empty(f'FOUP_{i:02d}',(0,-.18,1.32),port)
 box('FOUP_Base',(0,0,0),(.74,.65,.08),dark,f)
 box('FOUP_Amber_Shell',(0,0,.32),(.72,.62,.60),amber,f,.085)
 box('FOUP_Top',(0,0,.65),(.69,.59,.055),amber,f)
 box('FOUP_Handle',(0,0,.71),(.28,.23,.08),dark,f)
 box('FOUP_Door',(0,.32,.32),(.62,.035,.50),amber,f)
 for j in range(12):cyl('Wafer',(0,0,.09+j*.038),.15,.002,steel,f)
console=empty('Control_Console',par=root)
box('Console_Cabinet',(1.72,-.12,1.4),(.87,1.3,2.8),white,console)
box('Console_Header',(1.72,-.785,2.66),(.84,.025,.22),blue,console)
box('HMI_Bezel',(1.72,-.79,1.50),(.70,.035,.68),dark,console)
box('HMI_Screen',(1.72,-.814,1.50),(.63,.012,.59),glass,console)
box('Console_Shelf',(1.72,-.99,1.03),(.91,.49,.10),white,console)
cyl('Emergency_Stop_Collar',(1.44,-.83,1.10),.063,.025,yellow,console,True)
cyl('Emergency_Stop',(1.44,-.86,1.10),.038,.035,red,console,True)
cyl('Control_Selector',(1.94,-.84,1.10),.035,.025,dark,console,True)
tower=empty('Signal_Tower',(1.43,-.79,2.32),root)
for j,(n,m) in enumerate((('Green',green),('Yellow',yellow),('Red',red))):cyl(n,(0,0,j*.07),.035,.065,m,tower)
for side,x,s in (('Left',-2.47,-1),('Right',1.30,1)):
 door=empty('Safety_Door_'+side,(x,-.65,1.79),root);door.rotation_euler.z=s*math.radians(35)
 box('Safety_Window',(s*.30,0,0),(.54,.03,1.12),glass,door)
 for xx in (0,s*.60):box('Safety_Frame_V',(xx,0,0),(.06,.07,1.25),white,door)
 for z in (-.60,.60):box('Safety_Frame_H',(s*.30,0,z),(.65,.07,.06),white,door)
robot=empty('Wafer_Transfer_Robot',(-.5,.10,1.35),root)
cyl('Robot_Base',(0,0,.12),.2,.24,steel,robot)
j1=empty('Joint_01',(0,0,.28),robot);cyl('Joint_01_Cap',(0,0,0),.12,.10,dark,j1);box('Arm_01',(.36,0,0),(.72,.13,.07),steel,j1)
j2=empty('Joint_02',(.72,0,0),j1);j2.rotation_euler.z=math.radians(125);cyl('Joint_02_Cap',(0,0,0),.09,.11,dark,j2);box('Arm_02',(.32,0,.03),(.64,.10,.06),steel,j2)
w=empty('Wrist',(.64,0,.05),j2);box('End_Effector',(.24,0,0),(.48,.09,.02),steel,w)
lock=empty('Load_Lock',(0,.65,1.4),root);box('Load_Lock_Housing',(0,0,0),(.8,.7,.45),steel,lock);box('Load_Lock_Door',(0,-.37,0),(.6,.03,.25),dark,lock)
ch=empty('Process_Chamber',(.8,1.6,1.4),root);cyl('Chamber_Body',(0,0,0),.55,.6,steel,ch);box('Chamber_Door',(0,-.57,0),(.65,.04,.40),steel,ch);cyl('Wafer_Stage',(0,0,.33),.18,.04,dark,ch)
box('Auxiliary_Cabinet',(2.7,1.1,.58),(.65,.75,1.16),white)
for x in (-2.1,1.95):
 for y in (-.3,3.9):cyl('Leveling_Foot',(x,y,.04),.07,.08,steel)
root['provenance']='Reference-inspired concept exterior; simplified internal transfer components; dimensions not vendor CAD'
root['status']='Model only; independent moving parts; no animation'
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
bpy.ops.object.camera_add(location=(8,-10,6));cam=bpy.context.object;cam.name='Preview_Camera';cam.rotation_euler=(Vector((0,1.3,1.7))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=52;scene.camera=cam
for loc,power,size in [((1,-5,7),1800,6),((-5,1,6),1800,5),((4,5,7),2000,5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,1,1))-o.location).to_track_quat('-Z','Y').to_euler()
box('Preview_Ground',(0,1,-.10),(11,12,.10),mat('Floor',(.11,.13,.15)))
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(base,'Ion_Implanter_preview.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'Ion_Implanter.blend'))
print('MODEL_SAVED',len(root.children_recursive),'parts',len(bpy.data.actions),'actions')
bpy.ops.render.render(write_still=True)
