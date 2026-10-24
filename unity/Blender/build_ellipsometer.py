"""Reference-inspired virtual metrology station; not manufacturer CAD. No FOUP included.
Run inside the live Blender; preserve current work as a recovery copy first.
"""
import bpy, math, os, json
from mathutils import Vector

BASE = r'C:\Users\Administrator\Documents\Codex\UnityMOSFETFactory\Blender'
PATH = os.path.join(BASE, 'Ellipsometer_System.blend')
assert not os.path.exists(PATH), 'Existing ellipsometer must be edited, not overwritten by generator.'
if bpy.data.is_dirty:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BASE, 'Before_Ellipsometer_Recovery.blend'), copy=True)
scene = bpy.data.scenes.new('Ellipsometer_Design')
bpy.context.window.scene = scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1

def material(name, color, metal=0, rough=.35):
    m = bpy.data.materials.new('EL_' + name); m.diffuse_color=(*color,1); m.use_nodes=True
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=rough
    return m
white=material('Ivory_Powdercoat',(.73,.75,.72),.12)
purple=material('Indigo_Header',(.027,.014,.14),.2,.28)
steel=material('Brushed_Aluminium',(.45,.51,.54),.78,.32)
dark=material('Graphite',(.025,.034,.039),.3)
glass=material('Screen_Glass',(.012,.038,.048),.15,.2)
red=material('Stop_Red',(.65,.018,.012))
green=material('Status_Green',(.025,.52,.20))
yellow=material('Safety_Yellow',(.85,.55,.015))
blue=material('Status_Blue',(.04,.35,.65))
letter=material('Light_Lettering',(.85,.9,.91))

def group(name, loc=(0,0,0), par=None):
    o=bpy.data.objects.new(name,None); scene.collection.objects.link(o); o.parent=par; o.location=loc
    o.empty_display_size=.08
    return o
root=group('Ellipsometer_System')
root['purpose']='Reference-inspired virtual ellipsometry station; no FOUP, no wafer, no actual measurement.'
root['scale_reference']='Loader deck Z=1.10m, loading door Z=1.39m; furnace cabinet height approx 2.8m.'
root['front']='-Y; Z up; metres'
root['measurement_data']='TCAD predicted thickness; not measured data'

def box(name,loc,dims,mat,par=root,bevel=.008):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o=bpy.context.object;o.name=name;o.parent=par;o.location=loc;o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Edge_Radius','BEVEL');mod.width=min(bevel,min(dims)*.35);mod.segments=3
        mod=o.modifiers.new('Face_Normals','WEIGHTED_NORMAL')
    return o

def cyl(name,loc,r,depth,mat,par=root,front=False):
    bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=r,depth=depth)
    o=bpy.context.object;o.name=name;o.parent=par;o.location=loc
    if front:o.rotation_euler.x=math.pi/2
    o.data.materials.append(mat)
    q=o.modifiers.new('Edge_Radius','BEVEL');q.width=min(.003,depth*.2);q.segments=2
    for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
    o.modifiers.new('Face_Normals','WEIGHTED_NORMAL')
    return o

def text(name,body,loc,size,mat,par=root):
    d=bpy.data.curves.new(name,'FONT');d.body=body;d.size=size;d.align_x='CENTER';d.extrude=.0003
    o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.parent=par;o.location=loc;o.rotation_euler.x=math.pi/2
    d.materials.append(mat);return o

def strut(name,a,b,width,mat,par=root):
    a,b=Vector(a),Vector(b);o=box(name,(a+b)/2,(width,width,(b-a).length),mat,par)
    o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();return o

shell=group('Enclosure',par=root)
fixed=group('Fixed_Frame',par=root)
ports=group('LoadPorts',par=root)
box('Base_Plinth',(0,.52,.13),(2.36,2.08,.16),dark,fixed)
for x in (-1.04,1.04):
    for y in (-.35,1.38):
        cyl('Leveling_Foot',(x,y,.045),.065,.09,dark,fixed)
        cyl('Foot_Stem',(x,y,.105),.025,.05,steel,fixed)
        box('Frame_Post',(x,y,1.42),(.055,.055,2.46),steel,fixed)
box('Interior_Floor',(0,.52,.77),(2.24,1.91,.05),steel,fixed)
box('Rear_Panel',(0,1.535,1.49),(2.36,.045,2.50),white,shell)
box('Left_Panel',(-1.167,.53,1.49),(.045,1.96,2.50),white,shell)
for y,depth in ((-.13,.62),(.875,1.34)):
    box('Right_Service_Panel',(1.167,y,1.49),(.045,depth,2.50),white,shell)
box('Roof',(0,.53,2.75),(2.36,2.06,.08),white,shell)
for x in (-.79,0,.79):box('Front_Upper_Panel',(x,-.467,2.22),(.782,.045,.85),white,shell)
box('Front_Lower_Panel',(0,-.467,.63),(2.36,.045,.78),white,shell)
box('Front_Sill',(0,-.467,1.075),(2.36,.045,.08),white,shell)
box('Front_Door_Top_Fascia',(0,-.467,1.74),(2.36,.045,.10),white,shell)
# Fill the wall surrounding two true through-openings (0.78 x 0.50m).
for x,w in ((-1.075,.21),(0,.38),(1.075,.21)):
    box('Opening_Separator',(x,-.467,1.39),(w,.045,.55),white,shell)
for loc,dims in [((0,-.475,2.72),(2.38,.065,.17)),((0,1.555,2.72),(2.38,.065,.17)),((-1.185,.54,2.72),(.065,2.04,.17)),((1.185,.54,2.72),(.065,2.04,.17))]:
    box('Indigo_Header',loc,dims,purple,shell,.005)
text('Equipment_Name','ELLIPSOMETRY',(0,-.515,2.68),.115,letter)
text('Equipment_Subtitle','FILM METROLOGY',(0,-.50,2.48),.043,dark)

for index,x in enumerate((-.58,.58),1):
    port=group(f'LoadPort_{index:02}',(x,0,0),ports)
    box(f'LP{index}_Pedestal',(0,-.91,.56),(.91,.78,1.04),white,port,.045)
    box(f'LP{index}_Deck',(0,-1.005,1.10),(1.10,.79,.14),white,port,.035)
    box(f'LP{index}_Docking_Plate',(0,-1.005,1.18),(.82,.64,.022),steel,port,.02)
    for px,py in ((-.26,-1.21),(.26,-1.21),(0,-.80)):
        cyl(f'LP{index}_Docking_Pin',(px,py,1.205),.014,.028,steel,port)
    for px in (-.32,.32):cyl(f'LP{index}_Presence_Sensor',(px,-.95,1.196),.009,.008,dark,port)
    box(f'LP{index}_Operator_Window',(0,-1.313,1.178),(.34,.11,.012),glass,port,.005)
    box(f'LP{index}_Door_Gasket',(0,-.504,1.39),(.84,.012,.56),dark,port)
    # Gasket has a real centre opening, not a solid panel behind the moving door.
    gasket=bpy.data.objects.get(f'LP{index}_Door_Gasket');bpy.data.objects.remove(gasket,do_unlink=True)
    for loc,dims in [((-.41,-.504,1.39),(.026,.018,.55)),((.41,-.504,1.39),(.026,.018,.55)),((0,-.504,1.655),(.82,.018,.025)),((0,-.504,1.125),(.82,.018,.025))]:box(f'LP{index}_Gasket',loc,dims,dark,port,.003)
    door=group(f'LP{index}_Door_ANIM',(0,-.555,1.39),port)
    box(f'LP{index}_Door_Plate',(0,0,0),(.78,.035,.50),steel,door,.018)
    for z in (-.16,.16):
        cyl(f'LP{index}_Door_Lock',(0,-.023,z),.033,.010,steel,door,True)
        box(f'LP{index}_Lock_Slot',(0,-.03,z),(.018,.005,.003),dark,door,.001)
    for sx in (-.37,.37):
        for z in (-.22,.22):cyl('Door_Fastener',(sx,-.023,z),.005,.006,dark,door,True)
    box(f'LP{index}_Status_Housing',(0,-.507,1.78),(.94,.055,.10),white,port,.008)
    box(f'LP{index}_Status_Strip',(0,-.539,1.78),(.84,.01,.055),dark,port,.003)
    for i,m in enumerate((yellow,letter,blue,green,green,yellow,red)):
        cyl(f'LP{index}_Indicator_{i}',(-.33+i*.11,-.55,1.78),.013,.008,m,port,True)
    text(f'LP{index}_Label',f'LOAD PORT {index}',(0,-.55,1.86),.033,dark,port)
    box(f'LP{index}_Door_Lift_Rail',(0,-.27,.98),(.10,.08,.85),steel,port)
    group(f'FOUP_Dock_{index:02}',(0,-1.02,1.215),port)
    door['open_recess_y']=.085;door['open_drop_z']=-.60

# Exterior details match the reference's tall side service cabinet and console.
for y in (-.22,.27,1.20):
    box('Service_Handle',(1.201,y,1.55),(.035,.04,.20),dark,shell,.01)
for y in (-.30,.20,1.25):
    for z in (.55,2.36):box('Service_Hinge',(1.199,y,z),(.025,.05,.09),steel,shell,.004)
box('Side_Inspection_Window',(1.196,.10,1.94),(.012,.38,.37),glass,shell,.003)
for z in [.42+i*.032 for i in range(8)]:box('Side_Vent',(1.196,.94,z),(.014,.44,.012),dark,shell,.002)
for z in [.40+i*.036 for i in range(6)]:box('Front_Vent',(0,-.495,z),(.55,.014,.012),dark,shell,.002)
for x in (-1.13,1.13):
    for z in (.3,1.04,2.58):cyl('Panel_Screw',(x,-.495,z),.007,.006,steel,shell,True)

hmi=group('HMI',par=root)
cyl('HMI_Support_Post',(1.39,.44,.87),.055,1.6,steel,hmi)
strut('HMI_Swing_Bracket',(1.18,.10,1.95),(1.69,-.04,1.95),.06,steel,hmi)
box('HMI_Enclosure',(1.66,-.13,1.94),(.68,.20,.93),white,hmi,.04)
box('HMI_Bezel',(1.66,-.242,2.10),(.56,.025,.43),dark,hmi,.023)
box('HMI_Screen',(1.66,-.258,2.10),(.50,.008,.36),glass,hmi,.01)
text('HMI_Title','TCAD / VIRTUAL',(1.66,-.265,2.20),.034,letter,hmi)
text('HMI_Thickness','OXIDE THICKNESS',(1.66,-.265,2.12),.028,letter,hmi)
text('HMI_Ready','READY',(1.66,-.265,2.03),.044,green,hmi)
text('HMI_Disclaimer','PREDICTED - NOT MEASURED',(1.66,-.265,1.96),.018,letter,hmi)
cyl('Emergency_Collar',(1.66,-.25,1.79),.041,.022,yellow,hmi,True)
cyl('Emergency_Button',(1.66,-.27,1.79),.026,.028,red,hmi,True)
box('Keyboard_Tray',(1.66,-.32,1.59),(.63,.47,.045),white,hmi,.02)
box('Keyboard_Base',(1.61,-.36,1.62),(.42,.18,.013),dark,hmi,.006)
for row in range(4):
    for col in range(12):box('Keyboard_Key',(1.425+col*.033,-.425+row*.04,1.631),(.024,.027,.007),steel,hmi,.001)
box('Touchpad',(1.87,-.36,1.62),(.08,.13,.009),steel,hmi,.006)

internal=group('Internal_Metrology',par=root)
robot=group('Transfer_Robot',(0,.13,.48),internal)
cyl('Robot_Base',(0,0,.16),.16,.32,steel,robot)
lift=group('Robot_Lift_ANIM',(0,0,.77),robot)
cyl('Robot_Lift_Column',(0,0,-.20),.065,.48,dark,lift)
j1=group('Joint_01_ANIM',par=lift)
cyl('Joint_01_Cap',(0,0,0),.11,.07,steel,j1)
box('Arm_01',(.25,0,0),(.5,.11,.055),steel,j1,.025)
j2=group('Joint_02_ANIM',(.5,0,0),j1);j2.rotation_euler.z=math.radians(145)
cyl('Joint_02_Cap',(0,0,.025),.075,.08,dark,j2)
box('Arm_02',(.23,0,.025),(.46,.085,.045),steel,j2,.02)
wrist=group('Wrist_ANIM',(.46,0,.045),j2);wrist.rotation_euler.z=math.radians(80)
cyl('Wrist_Cap',(0,0,0),.048,.05,steel,wrist)
box('Blade_Stem',(.12,0,.012),(.24,.05,.012),steel,wrist,.004)
for sy in (-.045,.045):box('Blade_Fork',(.285,sy,.012),(.24,.025,.012),steel,wrist,.004)
group('Blade_Attach',(.31,0,.019),wrist)
stage=group('Measurement_Module',(0,.93,0),internal)
box('Stage_Base',(0,0,1.03),(.68,.60,.10),dark,stage)
sx=group('Stage_X_ANIM',(0,0,1.12),stage)
for y in (-.18,.18):box('X_Guide',(0,y,0),(.57,.025,.025),steel,sx)
sy=group('Stage_Y_ANIM',(0,0,.06),sx)
box('Stage_Carriage',(0,0,0),(.41,.40,.06),steel,sy)
cyl('Wafer_Chuck',(0,0,.11),.143,.06,dark,sy)
group('Measurement_Position',(0,0,.14),sy)
# Two opposed inclined optical heads focus on the empty 300mm wafer position.
for sign,name in ((-1,'Light_Source'),(1,'Optical_Detector')):
    foot=(sign*.72,.93,.81);head=(sign*.39,.93,1.72);focus=(0,.93,1.32)
    strut(name+'_Stand',foot,(sign*.72,.93,1.72),.06,steel,internal)
    strut(name+'_Bracket',(sign*.72,.93,1.72),head,.065,dark,internal)
    unit=box(name,head,(.14,.16,.30),dark,internal,.015)
    unit.rotation_euler=(Vector(focus)-Vector(head)).to_track_quat('-Z','Y').to_euler()
    lens=cyl(name+'_Lens',Vector(head)+(Vector(focus)-Vector(head)).normalized()*.16,.045,.035,glass,internal)
    lens.rotation_euler=(Vector(focus)-Vector(head)).to_track_quat('Z','Y').to_euler()
    group(name+'_Optical_Axis',head,internal)
root['animation_ready']='Separate load-port doors, robot joints, XY stage, attachment anchors. No clips yet.'

# Presentation belongs to a separate collection and is excluded from equipment dimensions.
presentation=bpy.data.collections.new('Presentation');scene.collection.children.link(presentation)
def move_presentation(o):
    for c in list(o.users_collection):c.objects.unlink(o)
    presentation.objects.link(o)
floor=box('Preview_Floor',(0,.25,-.055),(200,200,.10),material('Backdrop',(.22,.25,.28)),None,.0);move_presentation(floor)
bpy.ops.object.camera_add(location=(6,-9,5.1));cam=bpy.context.object;cam.name='Ellipsometer_Preview_Camera'
cam.rotation_euler=(Vector((.28,.1,1.35))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO';cam.data.ortho_scale=5.25;scene.camera=cam;move_presentation(cam)
for loc,power,size in [((1,-4,6),1200,5),((-4,-1,4),900,4),((3,4,6),1500,4)]:
    bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size
    o.rotation_euler=(Vector((0,0,1.4))-o.location).to_track_quat('-Z','Y').to_euler();move_presentation(o)
scene.world=bpy.data.worlds.new('Ellipsometer_World');scene.world.use_nodes=True
next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND').inputs['Color'].default_value=(.6,.65,.75,1)
next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND').inputs['Strength'].default_value=.35
scene.render.engine='CYCLES';scene.cycles.samples=32
scene.render.resolution_x=1400;scene.render.resolution_y=1200;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(BASE,'Ellipsometer_preview.png')
bpy.context.view_layer.update()
parts=list(root.children_recursive)
pts=[o.matrix_world@Vector(c) for o in parts if o.type=='MESH' for c in o.bound_box]
mins=[min(v[i] for v in pts) for i in range(3)];maxs=[max(v[i] for v in pts) for i in range(3)]
assert abs(mins[2])<.001 and 2.7<maxs[2]<2.9
assert not any(o.name.startswith('FOUP_') and o.type=='MESH' for o in parts)
root['dimensions_m']=json.dumps([maxs[i]-mins[i] for i in range(3)])
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.region_3d.view_perspective='CAMERA'
        area.spaces.active.overlay.show_extras=False
        area.spaces.active.shading.color_type='MATERIAL'
bpy.ops.object.select_all(action='DESELECT');root.select_set(True);bpy.context.view_layer.objects.active=root
# Write only this scene; no old equipment gets bundled into the standalone asset.
bpy.data.libraries.write(PATH,{scene},fake_user=True)
print('ELLIPSOMETER_SAVED',PATH,'bounds',mins,maxs,'parts',len(parts))
bpy.ops.wm.open_mainfile(filepath=PATH)
