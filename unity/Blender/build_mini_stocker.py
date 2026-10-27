"""Six-slot reference-inspired stocker. Preserves the live document and saves a standalone asset.
Internal transfer is a demo gantry, not a reconstruction of vendor internals.
"""
import bpy, math, json, os, datetime
from mathutils import Vector
BASE=r'C:/Users/Administrator/Documents/Codex/UnityMOSFETFactory/Blender'
PATH=os.path.join(BASE,'Mini_Stocker_6Slot.blend')
assert not os.path.exists(PATH),'Existing stocker must be edited, not replaced.'
engine=bpy.context.scene.render.engine
if bpy.data.is_dirty:
    recovery=os.path.join(BASE,'Before_Mini_Stocker_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.blend')
    bpy.ops.wm.save_as_mainfile(filepath=recovery,copy=True)
scene=bpy.data.scenes.new('Mini_Stocker_Exterior');bpy.context.window.scene=scene
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
model=bpy.data.collections.new('Mini_Stocker_Asset');scene.collection.children.link(model)
cover=bpy.data.collections.new('Stocker_Removable_Panels');model.children.link(cover)
samples=bpy.data.collections.new('Separate_FOUP_Examples');scene.collection.children.link(samples)
presentation=bpy.data.collections.new('Stocker_Presentation');scene.collection.children.link(presentation)

def link(o,col=model):
    for c in list(o.users_collection):c.objects.unlink(o)
    col.objects.link(o);return o

def mat(name,col,metal=0,rough=.35):
    m=bpy.data.materials.new('ST_'+name);m.use_nodes=True;m.diffuse_color=(*col,1)
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*col,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;return m
white=mat('Warm_White',(.73,.75,.73),.12,.37);steel=mat('Aluminium',(.48,.54,.58),.72,.3)
dark=mat('Graphite',(.025,.035,.043),.18,.4);screenmat=mat('HMI_Glass',(.012,.055,.073),.15,.25)
ink=mat('Lettering',(.055,.10,.13));light=mat('HMI_Text',(.65,.88,.88));red=mat('Red',(.65,.025,.012));amber=mat('Amber',(.9,.46,.018));green=mat('Green',(.04,.6,.22))

def group(name,loc=(0,0,0),parent=None,col=model):
    o=bpy.data.objects.new(name,None);col.objects.link(o);o.parent=parent;o.location=loc;o.empty_display_size=.045;return o
root=group('Mini_Stocker');root['purpose']='Six-slot compact demo stocker inspired by the supplied exterior photo. Not vendor CAD.'
root['units']='metres; Z up; front -Y';root['body_dimensions_m']=[2.30,1.50,2.85]
root['scale_reference']='Existing FOUP 0.40 x 0.38 x 0.386 m; existing ellipsometer approx 2.8 m high.'
root['storage_capacity']=6;root['animation_note']='No motion clips yet. Separate Z elevator, X slider, Y fork, doors, dock and slot anchors.'
body=group('Body',parent=root);doors=group('Front_Doors',parent=root);racks=group('Storage_Racks',parent=root);transfer=group('Transfer_System',parent=root)

def box(name,loc,dims,material,parent=body,col=model,bevel=.005):
    bpy.ops.mesh.primitive_cube_add(size=1);o=link(bpy.context.object,col);o.name=name;o.parent=parent;o.location=loc;o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(material)
    if bevel:
        b=o.modifiers.new('Small_Edge_Radius','BEVEL');b.width=min(bevel,min(dims)*.24);b.segments=3;o.modifiers.new('Face_Normals','WEIGHTED_NORMAL')
    return o

def cylinder(name,loc,r,depth,material,parent=body):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=r,depth=depth);o=link(bpy.context.object);o.name=name;o.parent=parent;o.location=loc;o.data.materials.append(material)
    b=o.modifiers.new('Small_Edge_Radius','BEVEL');b.width=min(.002,depth*.15);b.segments=2;o.modifiers.new('Face_Normals','WEIGHTED_NORMAL');return o

def text(name,value,loc,size,material,parent=body,col=model):
    d=bpy.data.curves.new(name,'FONT');d.body=value;d.size=size;d.align_x='CENTER';d.extrude=.0002
    o=bpy.data.objects.new(name,d);col.objects.link(o);o.parent=parent;o.location=loc;o.rotation_euler=(math.pi/2,0,0);d.materials.append(material);return o

# Thin independent panels leave an actual interior volume.
box('Base_Plinth',(0,0,.14),(2.30,1.50,.16),dark)
box('Base_Pan',(0,0,.26),(2.30,1.50,.08),white)
for x in [-.99,.99]:
    for y in [-.59,.59]:
        cylinder('Levelling_Foot',(x,y,.04),.06,.08,dark)
        cylinder('Foot_Screw',(x,y,.09),.022,.06,steel)
for x in [-1.10,1.10]:
    for y in [-.70,.70]:box('Frame_Upright',(x,y,1.53),(.055,.055,2.50),steel)
for z in [.32,2.43,2.80]:
    for y in [-.70,.70]:box('Frame_Crossbar',(0,y,z),(2.24,.045,.045),steel)
    for x in [-1.10,1.10]:box('Frame_Depth_Beam',(x,0,z),(.045,1.44,.045),steel)
box('Rear_Panel',(0,.734,1.52),(2.22,.032,2.44),white,col=cover)
box('Left_Panel',(-1.134,0,1.43),(.032,1.44,2.26),white,col=cover)
box('Right_Panel',(1.134,0,1.43),(.032,1.44,2.26),white,col=cover)
box('Roof_Panel',(0,0,2.83),(2.30,1.50,.04),white,col=cover)
# The upper service band remains an open aluminium frame, as in the reference.
box('Front_Header',(0,-.733,2.35),(2.24,.034,.15),white,col=cover)
for x,w in [(-.57,1.07),(.57,1.07)]:
    pivot=group('Front_Door_Left' if x<0 else 'Front_Door_Right',(x-w*.5,-.745,.33),doors)
    box('Maintenance_Door',(w*.5,0,.175),(w,.035,.35),white,pivot,col=cover)
    box('Door_Handle',(w-.11,-.028,.175),(.025,.028,.105),dark,pivot,col=cover)
# Upper front panel split around a genuine right-hand transfer opening.
box('Front_Main_Panel',(-.45,-.735,1.42),(1.32,.035,1.72),white,col=cover)
box('Front_Right_Lower',(.67,-.735,.78),(.86,.035,.44),white,col=cover)
box('Front_Right_Upper',(.67,-.735,1.94),(.86,.035,.68),white,col=cover)
box('Port_Left_Jamb',(.255,-.735,1.30),(.07,.04,.60),steel)
box('Port_Right_Jamb',(.885,-.735,1.30),(.07,.04,.60),steel)
box('Port_Upper_Jamb',(.57,-.735,1.595),(.70,.04,.035),steel)
box('Port_Right_Closure',(1.01,-.735,1.30),(.18,.035,.60),white,col=cover)
box('Port_Lower_Jamb',(.57,-.735,1.0),(.70,.04,.04),steel)
portdoor=group('Port_Door_ANIM',(.57,-.705,1.31),root)
box('Transfer_Port_Shutter',(0,0,-.01),(.64,.025,.59),dark,portdoor,col=cover)
portdoor['open_translation_local_m']=[0,0,.60]
text('Model_Name','Mini Stocker',(-.43,-.757,1.93),.125,ink,col=cover)
text('Capacity_Label','6 SLOT  /  FOUP STORAGE',(-.43,-.758,1.78),.039,ink,col=cover)
for x in [-1.04,.18,1.04]:
    for z in [.62,2.20]:
        screw=cylinder('Panel_Fastener',(x,-.762,z),.006,.006,steel);screw.rotation_euler.x=math.pi/2
# Side service doors and narrow louvers.
for y in [-.35,.35]:
    pivot=group('Side_Door_Pivot',(1.153,y-.29,.35),root)
    box('Side_Service_Door',(0,.29,.31),(.022,.56,.62),white,pivot,col=cover)
    box('Side_Handle',(.02,.48,.31),(.025,.025,.10),dark,pivot,col=cover)
for i in range(9):box('Vent_Slot',(1.156,.21,2.20+i*.016),(.005,.50,.006),dark)

slots=[]
for level,z in enumerate([.68,1.30,1.92],1):
    rack=group('Rack_%02d'%level,parent=racks)
    for column,x in enumerate([-.57,.57],1):
        pocket=group('Slot_%02d'%len(slots),(x,.32,z),rack)
        pocket['slot_id']='STK-%02d'%(len(slots)+1)
        # Clear central underside channel allows the fork to enter without intersecting a shelf slab.
        for side in [-1,1]:
            box('Slot_Support_Rail',(side*.196,0,-.025),(.045,.50,.05),steel,pocket)
            box('Slot_Rear_Stop',(side*.196,.25,.025),(.045,.018,.09),dark,pocket)
            box('Slot_Locator',(side*.18,.10,.006),(.015,.025,.012),dark,pocket)
        dock=group('Slot_%02d_DockPoint'%(len(slots)+1),parent=pocket);slots.append(dock)
        text('Slot_Label',pocket['slot_id'],(0,-.261,-.025),.028,ink,pocket)
for x in [-.86,-.28,.28,.86]:box('Rack_Spine',(x,.57,1.45),(.035,.04,2.13),steel,racks)

# Z elevator plus X travel axis and Y telescopic fork. All pivots have clean local axes.
rail=group('Vertical_Rail',parent=transfer)
for x in [-1.03,1.03]:
    box('Vertical_Extrusion',(x,-.39,1.45),(.065,.07,2.26),steel,rail)
    box('Vertical_Guide',(x,-.445,1.45),(.024,.018,2.18),dark,rail)
    cylinder('Vertical_Motor',(x,-.38,.38),.06,.14,dark,rail)
elevator=group('Elevator_Carriage',(0,-.40,.64),transfer)
box('Moving_X_Beam',(0,0,-.05),(2.12,.10,.10),steel,elevator)
box('X_Linear_Guide',(0,-.058,-.015),(2.02,.018,.025),dark,elevator)
for x in [-1.03,1.03]:box('Z_Bearing_Block',(x,0,0),(.11,.14,.16),dark,elevator)
slider=group('Horizontal_Slider',(-.57,0,.04),elevator)
box('X_Carriage_Block',(0,0,-.055),(.25,.13,.075),dark,slider)
fork=group('FOUP_Fork',parent=slider)
box('Fork_Base',(0,.04,-.033),(.28,.25,.035),steel,fork)
for x in [-.085,.085]:box('Fork_Finger',(x,.30,-.007),(.036,.58,.014),steel,fork,bevel=.002)
attach=group('FOUP_AttachPoint',(0,.32,0),fork)
# At rest the fork is retracted into the clear front transfer lane.
fork.location.y=-.18
for o,axis,travel in [(elevator,'Z',[.64,1.88]),(slider,'X',[-.57,.57]),(fork,'Y',[-1.02,.40])]:
    o['motion_axis']=axis;o['travel_local_m']=travel

port=group('OHT_Transfer_Port',(.57,-1.10,1.10),root)
box('Port_Pedestal',(0,.02,-.5925),(.52,.59,1.015),white,port)
box('Port_Deck',(0,0,-.075),(.69,.68,.02),white,port)
# A slot through the port plate also leaves room for the underside fork.
for x in [-.19,.19]:
    box('Dock_Support_Rail',(x,0,-.0225),(.065,.52,.045),steel,port)
    box('Dock_Rail_Riser',(x,0,-.055),(.065,.52,.04),steel,port)
for x in [-.25,.25]:
    for y in [-.23,.23]:cylinder('Port_Locator',(x,y,.018),.012,.036,dark,port)
portdock=group('FOUP_DockPoint',parent=port)
group('OHT_Grip_Clearance_Centre',(0,0,.386),port)
text('Port_Label','I/O 01',(0,-.346,-.12),.045,ink,port)
# Small independent HMI on the front left; retained as a separate mesh for a Unity display.
hmi=group('HMI_Assembly',(-.78,-.80,1.38),root)
box('HMI_Bezel',(0,0,0),(.36,.07,.25),dark,hmi)
box('HMI_Screen',(0,-.039,0),(.31,.008,.20),screenmat,hmi)
text('HMI_Text','STOCKER 01\nREADY\n6 STORAGE SLOTS',(0,-.045,.047),.027,light,hmi)
stop=cylinder('Emergency_Stop',(-.78,-.85,1.15),.027,.03,red);stop.rotation_euler.x=math.pi/2
signal=group('Signal_Tower',(.97,-.56,2.86),root)
cylinder('Tower_Stem',(0,0,.025),.013,.05,steel,signal)
for i,m in enumerate([green,amber,red]):cylinder('Tower_Segment',(0,0,.07+i*.052),.027,.05,m,signal)
cylinder('Tower_Cap',(0,0,.20),.029,.018,dark,signal)

# Reuse the existing FOUP geometry at its actual scale, as independent roots.
lib=os.path.join(BASE,'FOUP_300mm_Concept.blend')
with bpy.data.libraries.load(lib,link=False) as (src,dst):
    dst.objects=[n for n in src.objects if not n.startswith(('Preview','Area','Camera','Light'))]
loaded=[o for o in dst.objects if o]
froot=next(o for o in loaded if o.name.startswith('FOUP_300mm_Concept'))
family=[froot]+list(froot.children_recursive)
for o in family:
    if samples.objects.get(o.name) is None:samples.objects.link(o)
# A compact separate FOUP source hierarchy, with no scene ground/lights.
froot.name='FOUP_Example_01';froot.location=slots[0].matrix_world.translation
bpy.context.view_layer.update()
# matrices were not evaluated when the slots were built; use explicit design anchors for initial placement.
froot.location=(-.57,.32,.68)
for index,(x,z) in enumerate([(.57,1.30),(-.57,1.92)],2):
    copies={o:o.copy() for o in family}
    for original,copy in copies.items():
        samples.objects.link(copy);copy.name='Sample%02d_'%index+original.name
    for original,copy in copies.items():copy.parent=copies.get(original.parent)
    copies[froot].name='FOUP_Example_%02d'%index;copies[froot].location=(x,.32,z)

# Presentation only; excluded from model dimensions and future export.
floormat=mat('Preview_Floor',(.29,.33,.37),0,.65)
box('Stocker_Preview_Floor',(0,0,-.035),(200,200,.05),floormat,None,presentation,0)
bpy.ops.object.camera_add(location=(5.6,-8,4.6));camera=link(bpy.context.object,presentation);camera.name='Stocker_Preview_Camera'
camera.rotation_euler=(Vector((0,-.25,1.42))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=4.65;scene.camera=camera
for pos,power,size in [((1,-4,6),1300,4),((-4,-1,4),1000,3),((2,4,5),1500,3)]:
    bpy.ops.object.light_add(type='AREA',location=pos);o=link(bpy.context.object,presentation);o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,1.4))-o.location).to_track_quat('-Z','Y').to_euler()
scene.world=bpy.data.worlds.new('Stocker_World');scene.world.use_nodes=True
bg=next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.55,.64,.75,1);bg.inputs['Strength'].default_value=.4
scene.render.engine=engine;scene.render.resolution_x=1280;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(BASE,'Mini_Stocker_6Slot_exterior.png')
scene.view_settings.view_transform='AgX'
# A second scene exposes internals without deleting or changing exterior panels.
cut=scene.copy();cut.name='Mini_Stocker_Internal'
def layer_find(layer,name):
    if layer.name==name:return layer
    for c in layer.children:
        hit=layer_find(c,name)
        if hit:return hit
layer_find(cut.view_layers[0].layer_collection,cover.name).exclude=True
cut.render.filepath=os.path.join(BASE,'Mini_Stocker_6Slot_internal.png')
# Basic layout checks based on the design-space envelope, not certification of a physical machine.
bpy.context.view_layer.update()
assert len(slots)==6
for x in [-.57,.57]:
    assert abs(x)+.20<1.10
for z in [.68,1.30,1.92]:assert z+.386<2.80
assert .62-.386>.20
assert all(o.parent is not root for o in samples.objects if o.name.startswith('FOUP_Example'))
root['checks']='6 slots; 0.62 m shelf pitch; >0.23 m vertical carrier clearance; separate FOUP roots; clear external top pickup.'
manifest={'body_dimensions_m':[2.30,1.50,2.85],'total_depth_with_port_m':2.19,'slot_count':6,'foup_case_dimensions_m':[.4,.38,.386],
          'slot_base_positions_m':[[x,.32,z] for z in [.68,1.30,1.92] for x in [-.57,.57]],'io_dock_m':[.57,-1.10,1.10],
          'motion_parts':['Elevator_Carriage','Horizontal_Slider','FOUP_Fork','Port_Door_ANIM','Front_Door_Left','Front_Door_Right'],
          'note':'Reference-inspired exterior and simplified demo mechanics. No animation clips or Unity installation yet.'}
with open(os.path.join(BASE,'Mini_Stocker_6Slot_design.json'),'w',encoding='utf-8') as f:json.dump(manifest,f,indent=2)
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.overlay.show_extras=False;area.spaces.active.overlay.show_relationship_lines=False;area.spaces.active.shading.color_type='MATERIAL'
bpy.ops.object.select_all(action='DESELECT');root.select_set(True);bpy.context.view_layer.objects.active=root
bpy.data.libraries.write(PATH,{scene,cut},fake_user=True)
print('MINI_STOCKER_SAVED',PATH,'slots',len(slots),'model meshes',sum(o.type=='MESH' for o in root.children_recursive))
bpy.ops.wm.open_mainfile(filepath=PATH)
