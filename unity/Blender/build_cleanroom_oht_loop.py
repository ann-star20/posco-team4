"""Build a closed OHT loop from surveyed Unity docks; carrier and hoist remain separate.
Reference envelopes are presentation only and are excluded from FBX export.
"""
import bpy,math,os,json,datetime
from mathutils import Vector
BASE=r'C:/Users/Administrator/Documents/Codex/UnityMOSFETFactory'
PATH=os.path.join(BASE,'Blender','OHT_Cleanroom_Loop.blend')
assert not os.path.exists(PATH),'Edit the existing loop rather than overwrite it.'
data=json.load(open(os.path.join(BASE,'Blender','OHT_Unity_layout.json'),encoding='utf-8-sig'))
if bpy.data.is_dirty:bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BASE,'Blender','Before_OHT_Loop_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.blend'),copy=True)
engine=bpy.context.scene.render.engine
scene=bpy.data.scenes.new('OHT_Cleanroom_Loop');bpy.context.window.scene=scene;scene.unit_settings.system='METRIC'
model=bpy.data.collections.new('OHT_Loop_Asset');scene.collection.children.link(model)
preview=bpy.data.collections.new('OHT_Layout_Reference');scene.collection.children.link(preview)
payload=bpy.data.collections.new('Separate_FOUP_Preview');scene.collection.children.link(payload)
def move(o,c=model):
 for old in list(o.users_collection):old.objects.unlink(o)
 c.objects.link(o);return o
def mat(n,c,metal=0,rough=.32):
 m=bpy.data.materials.new('LOOP_'+n);m.diffuse_color=(*c,1);m.use_nodes=True;p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;return m
steel=mat('Rail_Aluminium',(.48,.54,.60),.72);white=mat('Carrier_White',(.79,.82,.84),.13);dark=mat('Graphite',(.022,.031,.04),.1);blue=mat('Blue_Trim',(.10,.27,.40),.25);green=mat('Status_Green',(.03,.65,.25));red=mat('Stop_Red',(.65,.02,.012));label=mat('Label',(.08,.15,.20))
def group(n,p=(0,0,0),par=None,col=model):
 o=bpy.data.objects.new(n,None);col.objects.link(o);o.parent=par;o.location=p;o.empty_display_size=.04;return o
root=group('OHT_Cleanroom_Loop')
root['note']='Reference-inspired OHT geometry for the current virtual fab, not manufacturer CAD. Movement and process events not yet connected.'
rail=group('Rail_System',par=root);supports=group('Rail_Support',par=rail)
def box(n,p,size,m,par=root,col=model,b=.006):
 bpy.ops.mesh.primitive_cube_add(size=1);o=move(bpy.context.object,col);o.name=n;o.parent=par;o.location=p;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if b:q=o.modifiers.new('Edge_Radius','BEVEL');q.width=min(b,min(size)*.24);q.segments=3;o.modifiers.new('Face_Normals','WEIGHTED_NORMAL')
 return o
def cyl(n,p,r,d,m,par=root):
 bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=r,depth=d);o=move(bpy.context.object);o.name=n;o.parent=par;o.location=p;o.data.materials.append(m);o.modifiers.new('Face_Normals','WEIGHTED_NORMAL');return o
def text(n,value,p,size,par=root,col=model):
 curve=bpy.data.curves.new(n,'FONT');curve.body=value;curve.size=size;curve.align_x='CENTER';curve.extrude=.0002;o=bpy.data.objects.new(n,curve);col.objects.link(o);o.parent=par;o.location=p;o.rotation_euler=(math.pi/2,0,math.pi);curve.materials.append(label);return o
# Survey uses Unity Y-up. Author with Blender Z-up: (X, -UnityZ, UnityY).
def B(p):return Vector((p['x'],-p['z'],p['y']))
ports=data['ports'];height=math.ceil((data['maxEquipmentHeight']+1.10+.65)*10)/10
xl=ports[0]['position']['x']-1.35;xr=min(data['floorMax']['x']-.45,max(o['max']['x'] for o in data['equipment'])+.55);r=.75;back=3.75
leftz=ports[0]['position']['z'];rightz=ports[-1]['position']['z']
path=[]
def add(x,z):
 p=Vector((x,-z,height))
 if not path or (p-path[-1]).length>1e-7:path.append(p)
frontStops=[(xl+r,leftz)]+[(p['position']['x'],p['position']['z']) for p in ports]+[(xr-r,rightz)]
for (xa,za),(xb,zb) in zip(frontStops,frontStops[1:]):
 n=max(2,math.ceil((xb-xa)/.13))
 for i in range(n):
  t=i/n;add(xa+(xb-xa)*t,za+(zb-za)*(t*t*(3-2*t)))
add(xr-r,rightz)
def arc(cx,cz,start,end):
 for i in range(1,25):
  a=start+(end-start)*i/24;add(cx+r*math.cos(a),cz+r*math.sin(a))
def line(xa,za,xb,zb):
 n=math.ceil(math.hypot(xb-xa,zb-za)/.13)
 for i in range(1,n+1):add(xa+(xb-xa)*i/n,za+(zb-za)*i/n)
arc(xr-r,rightz+r,-math.pi/2,0);line(xr,rightz+r,xr,back-r);arc(xr-r,back-r,0,math.pi/2)
line(xr-r,back,xl+r,back);arc(xl+r,back-r,math.pi/2,math.pi);line(xl,back-r,xl,leftz+r);arc(xl+r,leftz+r,math.pi,1.5*math.pi)
if (path[-1]-path[0]).length<1e-5:path.pop()
# A slotted channel permits an underhung trolley stem; wheels run inside on the bottom lips.
profile=[(-.16,.11),(.16,.11),(.16,-.11),(.05,-.11),(.05,-.075),(.125,-.075),(.125,.075),(-.125,.075),(-.125,-.075),(-.05,-.075),(-.05,-.11),(-.16,-.11)]
verts=[]
for i,p in enumerate(path):
 t=(path[(i+1)%len(path)]-path[(i-1)%len(path)]).normalized();side=Vector((-t.y,t.x,0))
 for n,z in profile:verts.append(p+side*n+Vector((0,0,z)))
faces=[];k=len(profile)
for i in range(len(path)):
 for j in range(k):faces.append((i*k+j,i*k+(j+1)%k,((i+1)%len(path))*k+(j+1)%k,((i+1)%len(path))*k+j))
mesh=bpy.data.meshes.new('Continuous_Slotted_Channel');mesh.from_pydata(verts,[],faces);mesh.update();
import bmesh
bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
o=bpy.data.objects.new('Rail_ClosedLoop',mesh);model.objects.link(o);o.parent=rail;mesh.materials.append(steel)
# A hidden centreline is retained for editing; mesh export excludes it.
curve=bpy.data.curves.new('OHT_Route_Centreline','CURVE');curve.dimensions='3D';sp=curve.splines.new('POLY');sp.points.add(len(path)-1)
for p,q in zip(path,sp.points):q.co=(*p,1)
sp.use_cyclic_u=True;route=bpy.data.objects.new('Route_Centreline',curve);model.objects.link(route);route.parent=rail;route.hide_render=True
# Braced rear-wall frame supports the ceiling beams without aisle columns.
rear_column_z=data['floorMax']['z']-.22
support_columns=[]
for i in range(7):
 x=xl+.8+(xr-xl-1.6)*i/6
 # Interpolate the actual sampled delivery path for precise hanger placement.
 front_points=[q for q in path if q.x>=xl+r-.001 and q.x<=xr-r+.001 and -q.y<rightz+.001]
 zfront=-min(front_points,key=lambda q:abs(q.x-x)).y
 yfront=-zfront
 beam_front=.68;beam_back=-rear_column_z
 box('Ceiling_Crossbeam_%02d'%i,(x,(beam_front+beam_back)*.5,height+.70),(.14,beam_front-beam_back,.14),steel,supports)
 for y in [yfront,-back]:
  box('Rail_Hanger',(x,y,height+.40),(.055,.055,.58),steel,supports)
  box('Hanger_Clamp',(x,y,height+.13),(.22,.27,.06),dark,supports)
 column_top=height+.63
 box('Rear_Support_Column_%02d'%i,(x,-rear_column_z,(column_top+.05)*.5),(.14,.14,column_top-.05),steel,supports)
 box('Rear_Column_Base_%02d'%i,(x,-rear_column_z,.025),(.38,.36,.05),steel,supports)
 box('Rear_Wall_Anchor_%02d'%i,(x,-data['floorMax']['z']+.065,height+.52),(.36,.05,.45),steel,supports)
 box('Rear_Wall_Tie_%02d'%i,(x,-(rear_column_z+data['floorMax']['z']-.065)*.5,height+.52),(.12,data['floorMax']['z']-.065-rear_column_z,.12),steel,supports)
 start=Vector((x,-rear_column_z,height-.70));end=Vector((x,-back,height+.63));delta=end-start
 brace=box('Rear_Knee_Brace_%02d'%i,(start+end)*.5,(.10,.10,delta.length),steel,supports)
 brace.rotation_euler=delta.to_track_quat('Z','Y').to_euler()
 for dx in [-.12,.12]:
  for dy in [-.11,.11]:box('Base_Anchor_Bolt',(x+dx,-rear_column_z+dy,.061),(.035,.035,.022),dark,supports,b=.003)
 support_columns.append({'x':x,'y':0,'z':rear_column_z})
for y in [.62,-back-.62,-rear_column_z]:box('Ceiling_Longitudinal',((xl+xr)*.5,y,height+.70),(xr-xl+.65,.10,.14),steel,supports)
# Independent stations and frame axes allow exact Unity installation.
for name,p in [('OHT_Frame_Origin',(0,0,0)),('OHT_Frame_Up',(0,0,1)),('OHT_Frame_Front',(0,1,0))]:group(name,p,root)
stations=group('Station_Anchors',par=root)
for i,p in enumerate(ports,1):
 dock=B(p['position']);station=group(p['id']+'_STOP',(dock.x,dock.y,height),stations);group(p['id']+'_DOCK_REFERENCE',dock,stations)
 box('Station_Number_Plate',(dock.x,dock.y+.22,height+.27),(.55,.025,.20),white,stations)
 text('Station_Label','%02d  '%i+p['id'].split('_')[0],(dock.x,dock.y+.238,height+.245),.075,stations)
# One reference-style vehicle, separate from the fixed rail. Its local origin follows the rail centreline.
start=path[min(range(len(path)),key=lambda i:(path[i]-Vector((ports[0]['position']['x'],-leftz,height))).length)]
carrier=group('OHT_Carrier',start,root);travel=group('Travel_Unit',par=carrier);body=group('OHT_Body',par=carrier)
box('Bogie_Frame',(0,0,-.01),(.60,.21,.05),steel,travel)
for x in [-.23,.23]:
 for y in [-.09,.09]:
  o=cyl('Travel_Wheel',(x,y,-.02),.055,.028,dark,travel);o.rotation_euler.x=math.pi/2
box('Suspension_Stem',(0,0,-.145),(.055,.055,.22),steel,travel)
box('Upper_Cover',(0,0,-.395),(.91,.73,.37),white,body,b=.04)
for y in [-.325,.325]:
 box('Body_Side_Shroud',(0,y,-.82),(.91,.08,.50),white,body,b=.035)
 box('Blue_Identity_Stripe',(0,y+(.043 if y>0 else -.043),-.54),(.67,.008,.035),blue,body)
for x in [-.405,.405]:box('Body_End_Shroud',(x,0,-.82),(.10,.59,.50),white,body,b=.025)
box('Body_Sensor',(0,.372,-.38),(.12,.016,.06),dark,body)
text('Vehicle_ID','OHT 01',(0,.373,-.40),.09,body)
button=cyl('Emergency_Stop',(.28,.38,-.66),.025,.025,red,body);button.rotation_euler.x=math.pi/2
indicator=cyl('Status_Light',(-.30,.378,-.33),.018,.06,green,body)
hoist=group('Hoist_Lift',par=carrier);box('Winch',(0,0,-.54),(.30,.32,.08),steel,hoist)
lift=group('Lift_Frame',(0,0,-.64),hoist);box('Lift_Plate',(0,0,.038),(.25,.23,.03),steel,lift)
grip=group('Gripper',par=lift);group('OHT_FOUP_AttachPoint',par=lift)
for sign,labelname in [(-1,'Left'),(1,'Right')]:
 jaw=group('Gripper_'+labelname,(sign*.095,0,0),grip)
 box('Jaw_Vertical',(0,0,-.005),(.018,.12,.07),dark,jaw,b=.002)
 box('Jaw_Hook',(-sign*.013,0,-.035),(.035,.12,.014),steel,jaw,b=.002)
belts=group('Hoist_Belts',par=carrier)
for sign,name in [(-1,'Left'),(1,'Right')]:
 group('Belt_Top_'+name,(sign*.10,0,-.54),carrier);group('Belt_Bottom_'+name,(sign*.10,0,.055),lift)
 box('Cable_'+name,(sign*.10,0,-.5625),(.020,.006,.045),dark,belts,b=.001)
carrier['travel_rail_height_m']=height;lift['hoist_axis']='local Z';lift['travel_attach_height_relative_to_rail_m']=-.64
# Reuse one carrier as a separate object, never permanently parent it to the vehicle.
with bpy.data.libraries.load(os.path.join(BASE,'Blender','FOUP_300mm_Concept.blend'),link=False) as (src,dst):dst.objects=[n for n in src.objects if not n.startswith(('Preview','Area','Camera','Light'))]
froot=next(o for o in dst.objects if o and o.name.startswith('FOUP_300mm_Concept'))
for o in [froot]+list(froot.children_recursive):payload.objects.link(o)
froot.name='OHT_Preview_FOUP';froot.location=(start.x,start.y,height-.64-.386)
# Actual measured equipment envelopes are an explicit preview layer, not exported equipment models.
refmat=mat('Reference_Envelope',(.46,.53,.57),.05,.55)
for obs in data['equipment']:
 a=B(obs['min']);b=B(obs['max']);centre=(a+b)*.5;size=Vector((abs(b.x-a.x),abs(b.y-a.y),abs(b.z-a.z)))
 box('REF_'+obs['name'],centre,size,refmat,None,preview,b=.015)
for p in ports:
 q=B(p['position']);box('REF_Dock_'+p['id'],q-Vector((0,0,.04)),(.58,.52,.08),white,None,preview)
box('Preview_Floor',(-1.5,-1.6,-.08),(23,9,.15),mat('Floor',(.27,.32,.36),0,.7),None,preview)
bpy.ops.object.camera_add(location=(17,19,18));cam=move(bpy.context.object,preview);cam.name='OHT_Loop_Preview_Camera';cam.rotation_euler=(Vector((-2,-1.8,3.2))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=24;scene.camera=cam
for pos,power,size in [((0,4,14),2300,8),((-10,-2,10),1800,7),((9,-5,13),2100,7)]:
 bpy.ops.object.light_add(type='AREA',location=pos);o=move(bpy.context.object,preview);o.data.energy=power;o.data.size=size;o.rotation_euler=(Vector((-2,-1,3))-o.location).to_track_quat('-Z','Y').to_euler()
scene.world=bpy.data.worlds.new('OHT_Loop_World');scene.world.use_nodes=True;next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND').inputs['Strength'].default_value=.5
scene.render.engine=engine;scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.filepath=os.path.join(BASE,'Blender','OHT_Cleanroom_Loop_preview.png')
# Closed, welded mesh and route/stop/height checks.
edgecounts={}
for face in faces:
 for a,b in zip(face,face[1:]+face[:1]):
  e=tuple(sorted((a,b)));edgecounts[e]=edgecounts.get(e,0)+1
assert all(n==2 for n in edgecounts.values())
for p in ports:
 target=Vector((p['position']['x'],-p['position']['z'],height));assert min((q-target).length for q in path)<1e-5
assert height-1.10-data['maxEquipmentHeight']>=.64
assert xl-.16>data['floorMin']['x'] and xr+.16<data['floorMax']['x']
out=os.path.join(BASE,'Assets','MOSFETInspection','Models','OHTLoop');os.makedirs(out,exist_ok=True)
manifest={'railHeight':height,'supportTop':height+.77,'curveRadius':r,'vehicleLowest':height-1.10,'clearanceOverHighestEquipment':height-1.10-data['maxEquipmentHeight'],'rightStraightEnd':xr-r,'rightRailEnd':xr,'supportColumns':support_columns,'pointCount':len(path),'closed':True,'points':[{'x':p.x,'y':p.z,'z':-p.y} for p in path],'ports':ports,'sourceScene':data['scene'],'note':'Static rail/carrier assembly; no live transport, ROS2, or automatic process handoff.'}
json.dump(manifest,open(os.path.join(out,'OHT_Loop_layout.json'),'w',encoding='utf-8'),indent=2)
# FBX keeps independent moving parts; text copies become meshes only for export.
items=[root]+list(root.children_recursive);copies=[];records={}
try:
 bpy.ops.object.select_all(action='DESELECT')
 for obj in items:
  if obj.type=='FONT':
   copy=obj.copy();copy.data=obj.data.copy();scene.collection.objects.link(copy);copy.name=obj.name+'_Export';bpy.context.view_layer.objects.active=copy;copy.select_set(True);bpy.ops.object.convert(target='MESH');copy.select_set(False);copies.append(copy)
 for obj in items+copies:
  if obj.type not in ['EMPTY','MESH']:continue
  obj.select_set(True)
  if obj.type=='MESH':
   for m in obj.data.materials:
    node=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');records[m.name]={'name':m.name,'color':list(node.inputs['Base Color'].default_value),'metallic':node.inputs['Metallic'].default_value,'roughness':node.inputs['Roughness'].default_value}
 bpy.context.view_layer.objects.active=root;bpy.ops.export_scene.fbx(filepath=os.path.join(out,'OHT_Cleanroom_Loop.fbx'),use_selection=True,object_types={'EMPTY','MESH'},apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False,use_triangles=True)
finally:
 for o in copies:bpy.data.objects.remove(o,do_unlink=True)
json.dump({'items':list(records.values())},open(os.path.join(out,'OHT_Loop_materials.json'),'w',encoding='utf-8'),indent=2)
root['rail_height_m']=height;root['closed_loop']=True;root['route_samples']=len(path);root['survey_file']='OHT_Unity_layout.json';root['minimum_payload_clearance_m']=manifest['clearanceOverHighestEquipment']
for area in bpy.context.screen.areas:
 if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA';area.spaces.active.overlay.show_extras=False;area.spaces.active.overlay.show_relationship_lines=False
bpy.ops.object.select_all(action='DESELECT');root.select_set(True);bpy.context.view_layer.objects.active=root
bpy.data.libraries.write(PATH,{scene},fake_user=True)
print('OHT_LOOP_BUILT',PATH,'height',height,'points',len(path),'clearance',manifest['clearanceOverHighestEquipment'])
bpy.ops.wm.open_mainfile(filepath=PATH)
