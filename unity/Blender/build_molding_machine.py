import bpy, math, os
from mathutils import Vector
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
base=os.path.dirname(__file__)
def mat(name,color,metal=0,rough=.3):
 m=bpy.data.materials.new(name);m.use_nodes=True;p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;return m
silver=mat('Satin_Silver',(.55,.59,.62),.65);dark=mat('Graphite',(.025,.032,.038),.25);window=mat('Smoked_Observation_Window',(.025,.033,.035),.2,.12);steel=mat('Machined_Steel',(.33,.39,.43),.85);red=mat('Emergency_Red',(.8,.015,.008));yellow=mat('Warning_Yellow',(.95,.65,.015));green=mat('Signal_Green',(.015,.55,.09));copper=mat('Leadframe_Copper',(.65,.35,.12),.8);epoxy=mat('Molded_Epoxy',(.018,.018,.02));blue=mat('Screen_DarkBlue',(.018,.055,.085),.15)
def empty(n,loc=(0,0,0),par=None):
 o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.parent=par;o.location=loc;o.empty_display_size=.10;return o
root=empty('Molding_Machine_ROOT');body=empty('Body_Static',par=root)
def box(n,loc,dims,m,par=body,b=.012):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if b:q=o.modifiers.new('Edge_Radius','BEVEL');q.width=b;q.segments=3
 return o
def cyl(n,loc,r,d,m,par=body,axis='Z'):
 bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=r,depth=d);o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.data.materials.append(m)
 if axis=='Y':o.rotation_euler.x=math.pi/2
 if axis=='X':o.rotation_euler.y=math.pi/2
 return o
def text(n,s,loc,size,m,par=body):
 bpy.ops.object.text_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.rotation_euler.x=math.pi/2;o.data.body=s;o.data.size=size;o.data.extrude=.001;o.data.materials.append(m);return o
# Panel shell rather than a solid block, preserving usable internal space.
box('Base_Plinth',(0,0,.09),(5.6,1.6,.18),silver)
box('Rear_Panel',(0,.775,1.15),(5.6,.05,2.0),silver)
for x in (-2.775,2.775):box('Side_Panel',(x,0,1.15),(.05,1.6,2.0),silver)
box('Rounded_Roof',(0,0,2.14),(5.6,1.6,.22),silver,b=.095)
for x in (-2.5,2.5):
 for y in (-.60,.60):cyl('Leveling_Foot',(x,y,.025),.065,.05,steel)
# Tall left service door and narrow output module flank three molding stations.
def door(name,x,width,height,z):
 hinge=empty(name,(x-width/2,-.815,z),root)
 box(name+'_Panel',(width/2,0,0),(width,.045,height),silver,hinge)
 box(name+'_Window',(width/2,-.029,.12),(width*.65,.012,height*.67),window,hinge,b=.065)
 box(name+'_Handle',(width-.07,-.08,0),(.035,.035,.25),dark,hinge,b=.014)
 for zz in (-height*.30,height*.30):box(name+'_Hinge',(.015,.01,zz),(.035,.055,.065),steel,hinge)
 return hinge
door('Input_Service_Door',-2.20,1.12,1.88,1.13)
door('HMI_Service_Door',-1.24,.76,1.88,1.13)
box('HMI_Bezel',(-1.24,-.865,1.69),(.65,.035,.46),steel)
box('HMI_Screen',(-1.24,-.888,1.69),(.54,.012,.35),blue)
for j in range(5):box('HMI_Status_Row',(-1.25,-.897,1.58+j*.05),(.39,.005,.009),green,b=.001)
cyl('HMI_EStop_Collar',(-1.56,-.90,1.84),.043,.018,yellow,axis='Y');cyl('HMI_EStop',(-1.56,-.92,1.84),.028,.035,red,axis='Y')
text('Equipment_Name','MOLDING SYSTEM',(-2.68,-.836,2.025),.095,blue)
for idx,x in enumerate((-.40,.48,1.36),1):
 station=empty(f'Molding_Station_{idx:02d}',(x,0,0),root)
 door(f'Station_{idx:02d}_Door',x,.85,.88,1.65)
 box('Lower_Station_Cabinet',(x,-.79,.58),(.85,.055,.80),silver)
 panel=empty(f'Station_{idx:02d}_Sloped_Control',(x,-.93,1.10),root);panel.rotation_euler.x=math.radians(20)
 box('Sloped_Control_Frame',(0,0,0),(.82,.12,.30),steel,panel)
 box('Sloped_Control_Face',(0,-.069,.015),(.59,.012,.21),silver,panel)
 cyl('Station_EStop_Collar',(-.34,-.09,.07),.035,.02,yellow,panel,'Y');cyl('Station_EStop',(-.34,-.11,.07),.022,.03,red,panel,'Y')
 for j in range(4):box('Station_Control_Key',(-.34+j*.065,-.09,-.10),(.025,.012,.018),dark,panel,b=.002)
 # Press assembly; upper mold carries its platen and is independently movable.
 for xx in (-.28,.28):
  for yy in (-.32,.32):cyl('Press_Guide_Column',(xx,yy,1.38),.025,.90,steel,station)
 box('Press_Fixed_Base',(0,0,.93),(.72,.76,.10),dark,station)
 box('Lower_Mold',(0,0,1.02),(.56,.52,.10),steel,station)
 upper=empty('Upper_Mold_Assembly',(0,0,1.55),station)
 box('Upper_Mold',(0,0,0),(.56,.52,.12),steel,upper)
 box('Upper_Platen',(0,0,.13),(.72,.72,.12),dark,upper)
 cyl('Press_Ram',(0,0,1.90),.07,.30,steel,station)
 tray=empty('Leadframe_Tray',(0,-.02,1.09),station)
 box('Tray_Rail_Left',(-.25,0,0),(.025,.65,.025),steel,tray)
 box('Tray_Rail_Right',(.25,0,0),(.025,.65,.025),steel,tray)
 box('Leadframe_Strip',(0,0,0),(.45,.55,.004),copper,tray)
 for r in range(3):
  for c in range(4):
   xx=-.165+c*.11;yy=-.17+r*.17
   box('MOSFET_Molded_Body',(xx,yy,.018),(.065,.09,.025),epoxy,tray,b=.004)
   for lead in (-1,0,1):box('MOSFET_Lead',(xx+lead*.018,yy-.065,.004),(.009,.045,.006),copper,tray,b=.001)
 # Roof pipe, riser, valve and sensor box.
 cyl('Roof_Riser',(x,0,2.30),.065,.20,steel)
 cyl('Roof_Pipe',(x,.15,2.37),.022,.63,steel,axis='Y')
 box('Valve_Block',(x,-.01,2.39),(.10,.09,.09),steel)
 cyl('Valve_Stem',(x,-.01,2.47),.012,.08,steel)
 cyl('Valve_Handwheel',(x,-.01,2.52),.05,.015,dark)
 box('Pressure_Sensor',(x,.25,2.47),(.105,.08,.10),steel)
 box('Pressure_Display',(x,.204,2.47),(.07,.008,.055),blue)
door('Output_Service_Door',2.02,.43,1.87,1.13)
door('Output_Module_Door',2.52,.49,1.40,1.30)
# Independent transport targets for future loading and unloading motion.
for name,x in [('Input_Transfer_Tray',-2.20),('Output_Transfer_Tray',2.50)]:
 t=empty(name,(x,0,1.03),root);box(name+'_Plate',(0,0,0),(.52,1.0,.035),steel,t)
 for i in range(5):box('Magazine_Shelf',(x,.20,.56+i*.13),(.50,.62,.025),steel)
box('Roof_Control_Box',(-1.15,.17,2.39),(.75,.62,.27),silver)
for i in range(7):box('Roof_Box_Vent',(-1.15,-.15,2.31+i*.025),(.54,.008,.008),dark,b=.001)
tower=empty('Signal_Tower',(-2.35,0,2.25),root);cyl('Tower_Stem',(0,0,.12),.025,.24,silver,tower)
for j,(name,m) in enumerate([('Green',green),('Yellow',yellow),('Red',red)]):cyl(name,(0,0,.26+j*.065),.045,.06,m,tower)
root['dimensions']='Concept enclosure 5.6 x 1.6 x 2.25 m; roof fittings extend above enclosure'
root['provenance']='Reference-inspired exterior; simplified demonstration press internals, not manufacturer CAD'
root['status']='MODELING_ONLY; independent doors, molds and trays; no animation'
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=1300;scene.render.resolution_y=850;scene.render.resolution_percentage=100
bpy.ops.object.camera_add(location=(7,-10,5));cam=bpy.context.object;cam.name='Preview_Camera';cam.rotation_euler=(Vector((0,0,1.25))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=53;scene.camera=cam
for loc,power,size in [((1,-5,7),2300,6),((-5,-2,5),1800,5),((3,4,6),2100,5)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
box('Preview_Ground',(0,0,-.08),(12,9,.10),mat('Floor',(.12,.14,.16)))
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(base,'Molding_Machine_preview.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'Molding_Machine.blend'))
print('MODEL_SAVED',len(root.children_recursive),'parts',len(bpy.data.actions),'actions')
bpy.ops.render.render(write_still=True)
