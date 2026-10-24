"""Retain the implanter envelope and build a separated, animatable end station."""
import bpy, math, os, json
from mathutils import Vector
base=os.path.dirname(__file__)
assert bpy.data.filepath.endswith('Ion_Implanter.blend'), 'Open the original implanter first.'
root=bpy.data.objects['Ion_Implanter']
def remove_tree(o):
    for child in list(o.children): remove_tree(child)
    bpy.data.objects.remove(o,do_unlink=True)
for name in ['Wafer_Transfer_Robot','Load_Lock','Process_Chamber']:
    remove_tree(bpy.data.objects[name])
for name in ['FOUP_%02d'%i for i in range(1,5)]:
    remove_tree(bpy.data.objects[name])
for name in ['Front_Upper_Cabinet','Front_Rear_Panel','Beamline_Link']:
    bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
for o in list(root.children_recursive):
    if o.name.startswith('Port_Door'): bpy.data.objects.remove(o,do_unlink=True)
def mat(name,color,metal=.0,rough=.35):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name);m.use_nodes=True
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
    m.diffuse_color=(*color,1);return m
white=bpy.data.materials['Clean_White'];steel=bpy.data.materials['Steel'];dark=bpy.data.materials['Graphite'];glass=bpy.data.materials['Dark_Window']
silicon=mat('Ion_Silicon',(.035,.10,.17),.55,.22);ceramic=mat('Ion_Ceramic',(.65,.67,.63),.1,.55)
def empty(n,p=(0,0,0),parent=root):
    o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.parent=parent;o.location=p;return o
def box(n,p,size,m=white,parent=root,bevel=.006):
    bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=parent;o.location=p;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
    if bevel: mod=o.modifiers.new('Edge_Radius','BEVEL');mod.width=bevel;mod.segments=3
    return o
def cyl(n,p,r,depth,m=steel,parent=root):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=r,depth=depth);o=bpy.context.object;o.name=n;o.parent=parent;o.location=p;o.data.materials.append(m)
    mod=o.modifiers.new('Edge_Radius','BEVEL');mod.width=.003;mod.segments=3
    for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
    return o
skin=empty('EFEM_Exterior')
box('Cut_Front_Upper',(-.6,-.59,2.30),(3.75,.06,1.05),parent=skin)
box('Cut_EFEM_Roof',(-.6,.17,2.82),(3.75,1.56,.04),parent=skin)
box('Cut_EFEM_Left',(-2.46,.17,1.45),(.04,1.56,2.70),parent=skin)
box('Cut_EFEM_Right',(1.26,.17,1.45),(.04,1.56,2.70),parent=skin)
box('EFEM_Floor',(-.6,.17,1.08),(3.72,1.55,.06),steel)
# Each port is an actual opening, surrounded by the same cabinet panel material.
for i,x in enumerate([-2,-1.05,-.1,.85],1):
    box('Cut_Port_Upper_%02d'%i,(x,-.59,1.72),(.94,.055,.11),parent=skin)
    box('Port_Lower_%02d'%i,(x,-.59,1.20),(.94,.055,.20))
    for side in [-1,1]:box('Port_Jamb_%02d'%i,(x+side*.345,-.59,1.50),(.25,.055,.40))
    d=empty('Port_%02d_Door_ANIM'%i,(x,-.625,1.50))
    box('Port_%02d_Door_Plate'%i,(0,0,0),(.425,.025,.36),steel,d)
    for xx in [-.12,.12]:
        latch=cyl('Port_Door_Latch',(xx,-.017,-.07),.018,.008,dark,d);latch.rotation_euler.x=math.pi/2
    empty('FOUP_Dock_%02d'%i,(x,-.92,1.30))
    # The source carrier remains a separate asset; only docking anchors are in this model.
for o in [bpy.data.objects['Safety_Door_Left'],bpy.data.objects['Safety_Door_Right']]:
    remove_tree(o)
# Partition between the atmosphere and vacuum machinery, with one transfer slot.
for x,w in [(-1.23,2.46),(1.03,.46)]:box('Vacuum_Bulkhead',(x,.97,1.50),(w,.045,.85),steel)
box('Vacuum_Bulkhead_Top',(.5,.97,1.88),(.60,.045,.12),steel)
box('Vacuum_Bulkhead_Bottom',(.5,.97,1.23),(.60,.045,.30),steel)
def robot(prefix,p,l1=.65,l2=.60):
    rob=empty(prefix,p);cyl(prefix+'_Base',(0,0,-.18),.13,.27,steel,rob)
    j1=empty(prefix+'_Joint1',(0,0,0),rob);cyl(prefix+'_J1_Cap',(0,0,0),.09,.06,dark,j1)
    box(prefix+'_Arm1',(l1/2,0,-.025),(l1,.09,.04),steel,j1)
    j2=empty(prefix+'_Joint2',(l1,0,0),j1);cyl(prefix+'_J2_Cap',(0,0,0),.07,.05,dark,j2)
    box(prefix+'_Arm2',(l2/2,0,-.010),(l2,.07,.035),steel,j2)
    w=empty(prefix+'_Wrist',(l2,0,0),j2);cyl(prefix+'_WristCap',(0,0,-.003),.055,.02,dark,w)
    box(prefix+'_BladeStem',(.075,0,-.002),(.15,.055,.002),ceramic,w,.001)
    for yy in [-.045,.045]:box(prefix+'_BladeFork',(.215,yy,-.002),(.20,.024,.002),ceramic,w,.001)
    empty(prefix+'_Contact',(.28,0,0),w)
    empty(prefix+'_Home',(.1,.1,1.49) if prefix=='ATM' else (.1,1.8,1.49))
    return rob
robot('ATM',(-.6,.20,1.49))
robot('VAC',(-.45,1.40,1.49),.65,.80)
# Three separated support lands leave room for the fork to enter below the wafer.
def chuck(n,p,parent=root):
    node=empty(n,p,parent);cyl(n+'_Pedestal',(0,0,-.09),.11,.12,steel,node)
    for xx in [-.105,0,.105]:box(n+'_Land',(xx,0,-.016),(.035,.13,.03),ceramic,node,.003)
    empty(n+'_Target',(0,0,0),node);return node
align=chuck('Aligner',(-1.65,.32,1.49));empty('Aligner_Rotate',(0,0,0),align)
lock=empty('LoadLock_Module',(.5,1.00,1.49))
box('Cut_LoadLock_Lid',(0,0,.19),(.56,.65,.035),steel,lock)
box('LoadLock_Floor',(0,0,-.15),(.56,.65,.04),steel,lock)
for xx in [-.27,.27]:box('Cut_LoadLock_Side',(xx,0,.02),(.025,.65,.33),steel,lock)
for name,yy in [('Outer',-.34),('Inner',.34)]:
    door=empty('LL_'+name+'_Door_ANIM',(0,yy,0),lock)
    box('LL_'+name+'_Gate',(0,0,0),(.50,.025,.15),dark,door)
    for xx in [-.26,.26]:box('LL_Guide',(xx,0,-.02),(.015,.045,.38),steel,door)
chuck('LoadLock_Chuck',(0,0,0),lock)
chamber=empty('Implant_Chamber',(.5,2.72,1.49))
box('Process_Floor',(0,0,-.21),(1.70,1.10,.06),steel,chamber)
box('Cut_Process_Lid',(0,0,.50),(1.70,1.10,.04),steel,chamber)
for xx in [-.84,.84]:box('Cut_Process_Side',(xx,0,.15),(.04,1.10,.70),steel,chamber)
box('Process_Rear',(0,.54,.15),(1.70,.035,.70),steel,chamber)
gate=empty('Process_Door_ANIM',(0,-.565,0),chamber);box('Process_Gate',(0,0,0),(1.60,.025,.18),dark,gate)
stage=chuck('Implant_Stage',(0,0,0),chamber)
pivot=empty('Implant_Tilt_Pivot',(0,0,0),stage)
for child in list(stage.children):
    if child!=pivot:child.parent=pivot
box('Stage_Scan_Rail',(0,0,-.15),(.65,.12,.06),dark,chamber)
# Beamline components are visible only in the explanatory cutaway.
beam=empty('Beamline_Internal')
for y in [3.55,3.95]:
    pipe=cyl('Beam_Tube',(.5,y,1.58),.10,.42,steel,beam);pipe.rotation_euler.x=math.pi/2
    flange=cyl('Beam_Flange',(.5,y-.21,1.58),.15,.035,steel,beam);flange.rotation_euler.x=math.pi/2
box('Analyzer_Magnet',(.5,3.95,1.58),(.50,.28,.46),dark,beam)
box('Ion_Source',(.5,4.19,1.58),(.40,.28,.35),steel,beam)
empty('Beam_Start',(.5,3.25,1.58));empty('Beam_End',(.5,2.72,1.49))
empty('Design_Origin');empty('Design_X',(1,0,0));empty('Design_Y',(0,1,0));empty('Design_Z',(0,0,1))
# A ready folded pose is serialized by Unity after the kinematic checks.
root['animation_note']='Manual single-wafer cycle; separate atmosphere/vacuum robots and interlocked loadlock gates. Project visualization, not vendor CAD.'
exec(compile(open(os.path.join(base,'update_ion_exterior.py'),encoding='utf-8').read(),'update_ion_exterior.py','exec'))
for obj in root.children_recursive:
    if obj.type=='MESH': assert all(math.isfinite(v) for v in obj.location)
scene=bpy.context.scene;scene.camera.location=(7,-10,6);scene.camera.rotation_euler=(Vector((-.2,1,1.6))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(base,'Ion_Implanter_Animated.blend'))
out=os.path.join(base,'..','Assets','MOSFETInspection','Models','FabEquipment');items=[root]+[o for o in root.children_recursive if not o.name.startswith('Preview_')]
bpy.ops.object.select_all(action='DESELECT');records={}
for o in items:
    o.select_set(True)
    if o.type=='MESH':
        for m in o.data.materials:
            p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
            records[m.name]={'name':m.name,'color':list(p.inputs['Base Color'].default_value),'metallic':p.inputs['Metallic'].default_value,'roughness':p.inputs['Roughness'].default_value}
bpy.context.view_layer.objects.active=root
bpy.ops.export_scene.fbx(filepath=os.path.join(out,'Ion_Implanter_Animated.fbx'),use_selection=True,object_types={'EMPTY','MESH'},apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False,use_triangles=True)
with open(os.path.join(out,'Ion_Animation_materials.json'),'w') as f:json.dump({'items':list(records.values())},f)
print('ION_MODEL_READY',len(items),'parts; original source retained')
