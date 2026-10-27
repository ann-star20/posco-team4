import bpy, math, os, json, datetime, bmesh
from mathutils import Vector
BASE=r'C:/Users/Administrator/Documents/Codex/UnityMOSFETFactory'
assert bpy.data.filepath.replace('\\','/').endswith('/Blender/OHT_Cleanroom_Loop.blend')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BASE,'Blender','Before_Rail_Extension_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.blend'),copy=True)
root=bpy.data.objects['OHT_Cleanroom_Loop'];rail=bpy.data.objects['Rail_System'];supports=bpy.data.objects['Rail_Support'];model=bpy.data.collections['OHT_Loop_Asset']
steel=bpy.data.materials['LOOP_Rail_Aluminium'];dark=bpy.data.materials['LOOP_Graphite']
data=json.load(open(os.path.join(BASE,'Blender','OHT_Unity_layout.json'),encoding='utf-8-sig'))
for o in list(supports.children_recursive)+[bpy.data.objects['Rail_ClosedLoop'],bpy.data.objects['Route_Centreline']]:bpy.data.objects.remove(o,do_unlink=True)
def box(n,p,size,m,par=root,col=model,b=.006):
 bpy.ops.mesh.primitive_cube_add(size=1);o=bpy.context.object
 for old in list(o.users_collection):old.objects.unlink(o)
 col.objects.link(o);o.name=n;o.parent=par;o.location=p;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(m)
 if b:q=o.modifiers.new('Edge_Radius','BEVEL');q.width=min(b,min(size)*.24);q.segments=3;o.modifiers.new('Face_Normals','WEIGHTED_NORMAL')
 return o
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

# Validate welded rail, support placement, room envelope, and process clearances.
bm=bmesh.new();bm.from_mesh(mesh);assert all(e.is_manifold for e in bm.edges);bm.free()
assert xr+.16<data['floorMax']['x'] and xl-.16>data['floorMin']['x']
for col in support_columns:
 for obs in data['equipment']:
  assert not (obs['min']['x']-.20<col['x']<obs['max']['x']+.20 and obs['min']['z']-.18<col['z']<obs['max']['z']+.18),('Support overlaps tool',obs['name'])
assert height-1.10-data['maxEquipmentHeight']>=.64
out=os.path.join(BASE,'Assets','MOSFETInspection','Models','OHTLoop')
f=os.path.join(out,'OHT_Loop_layout.json');manifest=json.load(open(f,encoding='utf-8'))
manifest.update(supportTop=height+.77,rightStraightEnd=xr-r,rightRailEnd=xr,supportColumns=support_columns,pointCount=len(path),points=[{'x':p.x,'y':p.z,'z':-p.y} for p in path])
json.dump(manifest,open(f,'w',encoding='utf-8'),indent=2)
root['route_samples']=len(path);root['rear_wall_grounded_supports']=7
bpy.ops.object.select_all(action='DESELECT');root.select_set(True);bpy.context.view_layer.objects.active=root
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BASE,'Blender','OHT_Cleanroom_Loop.blend'))
exec(compile(open(os.path.join(BASE,'Blender','export_cleanroom_oht_loop.py'),encoding='utf-8-sig').read(),'export_cleanroom_oht_loop.py','exec'))
print('RAIL_EXTENDED_WITH_GROUNDED_SUPPORTS',xr,'straightEnd',xr-r,'columns',len(support_columns),'points',len(path))
