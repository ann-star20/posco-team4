"""Add approved conceptual furnace details without replacing the existing loader or rig."""
import bpy, math, os, json, hashlib
from mathutils import Vector, Matrix
BASE=r'C:/Users/Administrator/Documents/Codex/UnityMOSFETFactory'
folder=os.path.join(BASE,'Tools/Oxidation');os.makedirs(folder,exist_ok=True)
assert not bpy.data.objects.get('Oxidation_Detailed_Addon'), 'Details already present'
original_file=bpy.data.filepath
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BASE,'Tools/Backups/OxidationDetailed-20261023/Blender-Before.blend'),copy=True)
system=bpy.data.objects['Oxidation_System'];loader=bpy.data.objects['Loader_Module'];boat=bpy.data.objects['Furnace_Boat_Elevator']
def signature(o):
    return (o.parent.name if o.parent else None,tuple(v for row in o.matrix_local for v in row),o.hide_render,tuple(m.name if m else '' for m in o.data.materials) if o.type=='MESH' else ())
loader_before={o.name:signature(o) for o in [loader]+list(loader.children_recursive)}
anchors=['Wafer_Robot_ROOT','Unity_Boat_Load_Contact','REF_LP2_Door_ANIM','Boat_Up_Target']
anchor_before={n:list(bpy.data.objects[n].matrix_world.translation) for n in anchors}
materials=[]
def mat(name,color,metal=0,smooth=.4):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*color,1)
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=1-smooth
    materials.append(dict(name=name,color=list(color),metallic=metal,smoothness=smooth));return m
white=mat('OXD_White',(.80,.83,.85),.08,.4);black=mat('OXD_Graphite',(.035,.045,.055),.2,.4)
steel=mat('OXD_Steel',(.42,.48,.53),.75,.65);quartz=mat('OXD_Quartz',(.54,.70,.76),.1,.65)
ceramic=mat('OXD_Insulation',(.74,.72,.66),0,.15);heater=mat('OXD_Heater',(.25,.27,.29),.6,.45)
screen=mat('OXD_Screen',(.025,.13,.23),.1,.7);blue=mat('OXD_ScreenInk',(.25,.60,.75),.05,.5)
red=mat('OXD_Red',(.65,.025,.015),.1,.4);yellow=mat('OXD_Yellow',(.85,.5,.02),0,.35)
root=bpy.data.objects.new('Oxidation_Detailed_Addon',None);bpy.context.collection.objects.link(root);root.parent=system
mobile=bpy.data.objects.new('OXD_BoatDetails',None);bpy.context.collection.objects.link(mobile);mobile.parent=root
new=[]
def box(name,center,size,material,parent=root,bevel=.003):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(material)
    if bevel:
        mod=o.modifiers.new('Machined edge','BEVEL');mod.width=bevel;mod.segments=2;bpy.ops.object.modifier_apply(modifier=mod.name)
    world=o.matrix_world.copy();o.parent=parent;o.matrix_world=world;new.append(o);return o
def cylinder(name,center,radius,depth,material,axis='Z',parent=root):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=radius,depth=depth,location=center);o=bpy.context.object;o.name=name
    if axis=='Y':o.rotation_euler.x=math.pi/2
    o.data.materials.append(material);world=o.matrix_world.copy();o.parent=parent;o.matrix_world=world;new.append(o);return o
def ring(name,z,r1,r2,height,material,start=0,end=2*math.pi,parent=root):
    count=48;verts=[];faces=[]
    for zz,r in [(z-height/2,r1),(z-height/2,r2),(z+height/2,r1),(z+height/2,r2)]:
        for i in range(count+1):
            a=start+(end-start)*i/count;verts.append((3+r*math.cos(a),.23+r*math.sin(a),zz))
    n=count+1
    for i in range(count):
        j=i+1;faces.extend([(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),(i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)])
    faces.extend([(0,n,3*n,2*n),(count,2*n+count,3*n+count,n+count)])
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);o.parent=parent;o.data.materials.append(material);new.append(o);return o
# Leave the transfer side wall and its existing opening untouched. Only front cosmetics are replaced.
hidden=[]
for o in list(system.children_recursive):
    if o.type!='MESH':continue
    if o.name.startswith(('Furnace_Control_','Furnace_Mimic_','Furnace_HMI_','Furnace_EStop_','Furnace_Loading_Frame','Furnace_Loading_Door_Panel','Furnace_Left_Control_Column','Furnace_Tower_','Furnace_Lamp_')) or o.name=='Furnace_Upper_Cabinet':
        hidden.append(o.name);o.hide_render=True;o.hide_set(True)
# The top/front and lower chamber covers disappear in the existing inside view.
door=box('OXD_CUT_MainDoor',(3,-.447,1.69),(1.17,.038,2.035),white)
for vertex in door.data.vertices:
    if vertex.co.z>0:vertex.co.z+=.090
box('OXD_CUT_LowerService',(3,-.449,.335),(1.17,.036,.59),white)
box('OXD_CUT_SideSeam',(3.613,.66,1.4),(.018,1.88,2.68),white)
box('OXD_CUT_TopLid',(3,.69,2.805),(1.22,2.01,.035),white)
# Door joints, hinges, recessed handle and screen are actual meshes, not painted imagery.
box('OXD_CUT_VerticalSeam',(3.25,-.469,1.69),(.007,.006,2.00),black,bevel=.001)
box('OXD_CUT_HandleRecess',(3.40,-.473,1.02),(.078,.014,.24),black)
box('OXD_CUT_HandleGrip',(3.40,-.491,1.02),(.021,.027,.18),steel)
box('OXD_CUT_HmiBezel',(2.76,-.483,1.66),(.40,.045,.25),black,bevel=.008)
box('OXD_CUT_HmiGlass',(2.76,-.509,1.66),(.35,.008,.205),screen)
for i in range(4):box('OXD_CUT_HmiLine_'+str(i),(2.74,-.515,1.72-i*.038),(.24 if i==0 else .18,.003,.009),blue,bevel=.001)
cylinder('OXD_CUT_EstopCollar',(2.66,-.49,1.38),.051,.025,yellow,'Y')
cylinder('OXD_CUT_Estop',(2.66,-.519,1.38),.034,.04,red,'Y')
for z in [.80,2.56]:box('OXD_CUT_Hinge_'+str(z),(2.43,-.48,z),(.027,.027,.09),steel)
for row in range(5):
    for col in range(8):box('OXD_CUT_Vent_%d_%d'%(row,col),(2.64+col*.10,-.471,.18+row*.037),(.065,.007,.012),black,bevel=.004)
for x in [2.46,3.54]:
    for z in [.07,.61,.72,2.66]:cylinder('OXD_CUT_PanelScrew',(x,-.47,z),.006,.006,steel,'Y')
# Text converted to mesh for deterministic export.
bpy.ops.object.text_add(location=(3.29,-.475,2.52),rotation=(math.pi/2,0,0));o=bpy.context.object;o.name='OXD_CUT_EquipmentID';o.data.body='OX-01';o.data.size=.065;o.data.extrude=.0004;o.data.materials.append(black);bpy.ops.object.convert(target='MESH');o=bpy.context.object;o.parent=root;new.append(o)
# Half shells make the heater visible in the cutaway, with a clear bore for the moving boat.
for a,b,suffix in [(0,math.pi,'Rear'),(math.pi,2*math.pi,'Front')]:
    prefix='OXD_CUT_' if suffix=='Front' else 'OXD_'
    ring(prefix+'Insulation_'+suffix,2.07,.255,.345,1.12,ceramic,a,b)
    ring(prefix+'Heater_'+suffix,2.07,.238,.253,1.10,heater,a,b)
for z in [1.50,2.63]:ring('OXD_ProcessFlange',z,.221,.275,.027,steel)
for x in [2.66,3.34]:
    box('OXD_InternalRail',(x,.49,1.15),(.04,.05,.76),steel)
    for z in [.82,1.46]:cylinder('OXD_GuideMount',(x,.49,z),.043,.025,steel)
# Add boat slot ledges outside the central blade corridor. No simulated extra wafers are added.
for i in range(12):
    z=.880+i*.038
    for a in [0,2*math.pi/3,4*math.pi/3]:
        x=3+.165*math.cos(a);y=.23+.165*math.sin(a)
        box('OXD_BoatLedge_%02d'%i,(x,y,z-.003),(.020,.022,.006),quartz,mobile,bevel=.001)
ring('OXD_BoatBaseRim',.81,.185,.205,.018,steel,parent=mobile)
# Anchor markers let Unity validate alignment independently of FBX import scale/orientation.
for i,n in enumerate(anchors):
    o=bpy.data.objects.new('OXD_Anchor'+str(i),None);bpy.context.collection.objects.link(o);o.parent=root;o.location=anchor_before[n]
for n,s in loader_before.items():assert signature(bpy.data.objects[n])==s, 'Loader modified: '+n
for n,p in anchor_before.items():assert (bpy.data.objects[n].matrix_world.translation-Vector(p)).length<1e-6
bpy.context.view_layer.update()
export=os.path.join(BASE,'Assets/MOSFETInspection/Models/FabEquipment/Oxidation_Detailed_Addon.fbx')
bpy.ops.object.select_all(action='DESELECT')
for o in [root]+list(root.children_recursive):o.hide_set(False);o.select_set(True)
bpy.context.view_layer.objects.active=root
bpy.ops.export_scene.fbx(filepath=export,use_selection=True,object_types={'EMPTY','MESH'},axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False)
# The original Blender rig also drives the added ledges.
world=mobile.matrix_world.copy();mobile.parent=boat;mobile.matrix_world=world
manifest=dict(hidden_original_renderers=hidden,materials=materials,anchor_names=anchors,loader_objects_unchanged=len(loader_before),added_meshes=len(new),source_file=original_file,note='Approved project concept; not an exact commercial product replica')
with open(os.path.join(BASE,'Assets/MOSFETInspection/Models/FabEquipment/Oxidation_Detailed_Addon.json'),'w',encoding='utf-8') as f:json.dump(manifest,f,indent=2)
for n,s in loader_before.items():assert signature(bpy.data.objects[n])==s
target_file=os.path.join(BASE,'Blender/Oxidation_System_Detailed.blend')
bpy.ops.wm.save_as_mainfile(filepath=target_file)
print('OXIDATION_BLENDER_DETAIL_OK',len(new),'meshes; loader preserved',len(loader_before),'objects; anchors preserved; saved',target_file)
