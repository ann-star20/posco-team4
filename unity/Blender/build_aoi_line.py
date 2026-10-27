import bpy,math,os
from mathutils import Vector
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
base=os.path.dirname(__file__)
def mat(n,c,metal=0,rough=.3):
 m=bpy.data.materials.new(n);m.use_nodes=True;p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;return m
white=mat('Powder_White',(.8,.84,.87),.1);steel=mat('Aluminum',(.45,.51,.55),.75);dark=mat('Graphite',(.022,.03,.038));belt=mat('Green_Belt',(.025,.23,.12));green=mat('OK_Green',(.02,.6,.13));red=mat('NG_Red',(.72,.018,.01));black=mat('Black_Epoxy',(.014,.018,.022));glass=mat('Smoked_Window',(.035,.07,.09),.2,.12);led=mat('LED_White',(.9,.95,1));yellow=mat('Safety_Yellow',(.95,.65,.02))
def empty(n,loc=(0,0,0),par=None):
 o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.parent=par;o.location=loc;o.empty_display_size=.08;return o
root=empty('AOI_Inspection_Line')
def box(n,loc,dims,m,par=root,b=.008):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if b:q=o.modifiers.new('Edge_Bevel','BEVEL');q.width=b;q.segments=2
 return o
def cyl(n,loc,r,d,m,par=root,front=False):
 bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=r,depth=d);o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.data.materials.append(m)
 if front:o.rotation_euler.x=math.pi/2
 return o
def label(n,s,loc,size,m,par=root):
 bpy.ops.object.text_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.rotation_euler.x=math.pi/2;o.data.body=s;o.data.align_x='CENTER';o.data.size=size;o.data.extrude=.001;o.data.materials.append(m);return o
def part(n,loc,par,scale=1):
 p=empty(n,loc,par);box('MOSFET_Body',(0,0,.0015),(.010,.009,.003),black,p,.0006);box('MOSFET_Tab',(-.004,0,.0005),(.006,.009,.001),steel,p,.0002)
 for j in (-1,0,1):box('MOSFET_Lead',(.009,j*.0025,0),(.009,.0008,.0006),steel,p,.0001)
 p.scale=(scale,)*3;return p
def conveyor(n,x,length,par):
 e=empty(n,(x,0,0),par);box('Conveyor_Frame',(0,0,.88),(length,.25,.08),steel,e);box('Conveyor_Belt',(0,0,.925),(length,.20,.01),belt,e)
 for y in (-.105,.105):box('Guide_Rail',(0,y,.95),(length,.02,.04),steel,e)
 return e
def feet(par,xs,ys):
 for x in xs:
  for y in ys:box('Support_Leg',(x,y,.44),(.045,.045,.82),steel,par);cyl('Leveling_Foot',(x,y,.035),.04,.04,dark,par)
# Input buffer with open hopper and single-product escapement.
buf=empty('MOSFET_Input_Buffer',(-1.75,0,0),root)
feet(buf,(-.42,.42),(-.34,.34));box('Buffer_Lower_Cabinet',(0,0,.43),(.86,.68,.65),white,buf)
conveyor('Buffer_Output_Conveyor',.48,.9,buf)
for x in (-.43,.43):
 for y in (-.34,.34):box('Hopper_Frame_Post',(x,y,1.26),(.035,.035,.86),steel,buf)
for y in (-.33,.33):
 p=box('Hopper_Slope',(0,y*.45,1.43),(.78,.035,.46),steel,buf);p.rotation_euler.x=math.copysign(math.radians(35),y)
for x in (-.39,.39):box('Hopper_End_Wall',(x,0,1.50),(.025,.65,.39),steel,buf)
box('Vibration_Feeder',(0,0,1.03),(.66,.43,.14),dark,buf)
rail=box('Feeder_Alignment_Track',(.25,0,1.10),(.72,.12,.045),steel,buf);rail.rotation_euler.y=math.radians(15)
esc=empty('Buffer_Escapement',(.66,0,.97),buf);box('Escapement_Stopper',(0,0,0),(.018,.13,.05),yellow,esc)
for i in range(35):part('Hopper_Product',(-.29+(i%7)*.09,-.20+(i//7)*.09,1.48+(i%3)*.015),buf,2.8)
box('Buffer_HMI_Bezel',(.55,-.45,1.38),(.32,.06,.25),white,buf);box('Buffer_HMI_Screen',(.55,-.486,1.38),(.26,.012,.18),glass,buf)
# AOI cabinet, intentionally hollow around inspection volume.
aoi=empty('AOI_Machine',(0,0,0),root)
feet(aoi,(-.63,.63),(-.43,.43));box('AOI_Lower_Cabinet',(0,0,.45),(1.4,.95,.72),white,aoi)
box('AOI_Rear_Wall',(0,.47,1.38),(1.4,.04,.92),white,aoi);box('AOI_Roof',(0,0,1.85),(1.48,1.02,.10),white,aoi)
for x in (-.70,.70):
 box('AOI_Side_Upper',(x,0,1.48),(.04,.95,.65),white,aoi)
 box('AOI_Side_Lower',(x,0,.79),(.04,.95,.12),white,aoi)
door=empty('AOI_Front_Door',(-.70,-.50,1.38),aoi)
box('AOI_Door_Frame',(.70,0,0),(1.40,.04,.85),dark,door)
box('AOI_Observation_Window',(.70,-.025,0),(1.15,.012,.62),glass,door,.045)
box('AOI_Door_Handle',(1.29,-.065,0),(.035,.04,.22),steel,door)
conv=conveyor('Inspection_Conveyor',0,1.40,aoi)
stage=box('Inspection_Stage',(0,0,.91),(.20,.18,.02),dark,aoi)
# Two narrow belt lanes leave a central slot for the vertical stopper.
o=bpy.data.objects.get('Conveyor_Belt.001')
if o:o.hide_render=True;o.hide_viewport=True
for y in (-.065,.065):box('Inspection_Belt_Lane',(0,y,.925),(1.4,.055,.01),belt,aoi)
stop=empty('Inspection_Stopper',(.12,0,.95),aoi);box('Stopper_Finger',(0,0,0),(.025,.04,.05),steel,stop)
cyl('Stopper_Pneumatic_Actuator',(.12,0,.80),.025,.12,steel,aoi)
camera=empty('Inspection_Camera',(0,0,1.43),aoi)
box('Camera_Body',(0,0,0),(.10,.10,.14),dark,camera);cyl('Camera_Lens',(0,0,-.105),.0275,.07,steel,camera);cyl('Camera_Lens_Glass',(0,0,-.142),.023,.005,glass,camera)
box('Camera_Bracket',(0,.14,1.49),(.04,.04,.30),steel,aoi);box('Camera_Crossbar',(0,.07,1.56),(.12,.20,.035),steel,aoi)
lighting=empty('Inspection_Lighting',par=aoi)
for y in (-.19,.19):
 l=box('LED_Housing',(0,y,1.21),(.18,.04,.025),dark,lighting);l.rotation_euler.x=math.copysign(math.radians(25),y)
 box('LED_Diffuser',(0,y,1.193),(.16,.032,.009),led,l if False else lighting)
box('Arrival_Photoelectric_Sensor',(-.20,-.15,.97),(.04,.035,.05),dark,aoi)
part('Inspection_MOSFET',(0,0,.935),aoi)
box('AOI_HMI_Arm',(.88,-.36,1.33),(.36,.045,.045),steel,aoi)
box('AOI_HMI_Bezel',(.99,-.50,1.41),(.44,.06,.34),dark,aoi);box('AOI_HMI_Screen',(.99,-.536,1.41),(.39,.012,.28),glass,aoi)
label('AOI_Label','AOI INSPECTION',(0,-.535,1.78),.08,white,aoi)
for j,m in enumerate((green,yellow,red)):cyl('AOI_Tower_Segment',(.55,.22,1.98+j*.06),.035,.055,m,aoi)
# Output sorter and two pull-out tray cabinets with separate chutes.
sorter=empty('OK_NG_Sorter',(1.62,0,0),root);conveyor('Sorter_Conveyor',0,1.65,sorter)
feet(sorter,(-.64,.64),(.28,.55))
act=empty('Sorter_Pusher',(-.22,.18,.97),sorter);box('Pusher_Cylinder',(0,.10,0),(.12,.20,.10),steel,act);box('Pusher_Rod',(0,-.06,0),(.025,.20,.025),steel,act);box('Pusher_Head',(0,-.17,0),(.12,.025,.05),yellow,act)
for name,x,color in [('OK',-.36,green),('NG',.36,red)]:
 c=empty(name+'_Collection_Cabinet',(x,-.54,0),sorter)
 # 450 x 500 mm cabinet, 600 mm high.
 box(name+'_Rear',(0,.24,.34),(.45,.025,.60),white,c)
 for xx in (-.215,.215):box(name+'_Side',(xx,0,.34),(.02,.50,.60),steel,c)
 box(name+'_Bottom',(0,0,.06),(.45,.50,.035),steel,c)
 drawer=empty(name+'_Tray_Drawer',(0,0,.24),c)
 box(name+'_Drawer_Front',(0,-.26,0),(.45,.025,.36),white,drawer)
 box(name+'_Label_Plate',(0,-.278,.10),(.30,.012,.075),color,drawer)
 label(name+'_Text',name,(0,-.289,.083),.055,white,drawer)
 box(name+'_Indicator',(0,-.285,.025),(.20,.012,.016),color,drawer)
 box(name+'_Handle',(.15,-.30,-.045),(.022,.035,.10),dark,drawer)
 tray=empty(name+'_Removable_Tray',(0,0,.13),drawer)
 box(name+'_Tray_Base',(0,0,0),(.40,.30,.01),dark,tray)
 for xx in (-.195,.195):box('Tray_Edge',(xx,0,.02),(.01,.30,.04),dark,tray)
 for yy in (-.145,.145):box('Tray_Edge',(0,yy,.02),(.40,.01,.04),dark,tray)
 for row in range(3):
  for col in range(4):
   xx=-.145+col*.096;yy=-.095+row*.095
   box('Tray_Pocket',(xx,yy,.008),(.080,.077,.008),steel,tray,.004);part('Tray_MOSFET',(xx,yy,.018),tray,2.8)
 for xx in (-.225,.225):box(name+'_Upper_Clear_Guard',(xx,0,.78),(.008,.50,.30),glass,c)
 chute=box(name+'_Inclined_Chute',(0,.10,.80),(.29,.40,.018),steel,c);chute.rotation_euler.x=math.radians(35)
 for xx in (-.18,.18):
  for yy in (-.19,.19):cyl('Cabinet_Foot',(xx,yy,.025),.028,.035,dark,c)
 cyl(name+'_Status_Beacon',(-.19,.18,.99),.018,.07,color,c)
root['status']='Modeling only, no animation. Camera housing is visual; Jetson capture integration is external.'
root['scale_note']='Industrial modules conceptual dimensions. Hopper/tray display products enlarged 2.8x; inspection MOSFET at nominal 10mm body scale.'
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=1500;scene.render.resolution_y=900;scene.render.resolution_percentage=100
bpy.ops.object.camera_add(location=(6,-8,4.5));cam=bpy.context.object;cam.name='Preview_Camera';cam.rotation_euler=(Vector((-.05,0,.95))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=52;scene.camera=cam
for loc,power,size in [((1,-4,6),1800,5),((-4,-1,4),1500,4),((2,4,5),1700,4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
box('Preview_Floor',(0,0,-.08),(10,7,.10),mat('Floor',(.12,.14,.16)))
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(base,'AOI_Inspection_Line_preview.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'AOI_Inspection_Line.blend'))
print('MODEL_SAVED',len(root.children_recursive),'parts',len(bpy.data.actions),'actions')
bpy.ops.render.render(write_still=True)
