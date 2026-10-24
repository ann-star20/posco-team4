"""Restyle the existing FOUP in place; preserve every object, pivot and wafer mesh."""
import bpy, bmesh, os, json, hashlib
from mathutils import Matrix, Vector

BASE=os.path.dirname(os.path.dirname(__file__))
root=bpy.data.objects['FOUP_300mm_Concept']
parts=[root]+list(root.children_recursive)
poses={o.name:tuple(v for row in o.matrix_local for v in row) for o in parts}
def digest(o):
    return hashlib.sha256(str([(tuple(v.co),) for v in o.data.vertices]).encode()).hexdigest()
wafers={o.name:digest(o) for o in parts if o.type=='MESH' and o.name.startswith('Wafer_')}
def shader(name,color,rough,trans=0):
    mat=bpy.data.materials[name];mat.use_nodes=True;mat.diffuse_color=color
    p=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color[:3],1)
    p.inputs['Roughness'].default_value=rough;p.inputs['Transmission Weight'].default_value=trans
    p.inputs['IOR'].default_value=1.46
shader('FOUP_Amber_Polymer',(1.0,.23,.025,.64),.20,.72)
bpy.data.materials['FOUP_Amber_Polymer'].diffuse_color=(1.0,.23,.025,1)
polymer=next(n for n in bpy.data.materials['FOUP_Amber_Polymer'].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
polymer.inputs['Base Color'].default_value=(1,.23,.025,.55)
polymer.inputs['Alpha'].default_value=.55
polymer.inputs['Transmission Weight'].default_value=.30
shader('FOUP_Door_Polymer',(.065,.085,.095,1),.30)
shader('FOUP_Slot_Rails',(.025,.032,.038,1),.43)

def detail_box(bm,owner,center,size,material_index):
    result=bmesh.ops.create_cube(bm,size=1)
    inv=owner.matrix_world.inverted()
    for v in result['verts']:v.co=inv@Vector(tuple(center[i]+v.co[i]*size[i] for i in range(3)))
    for f in {f for v in result['verts'] for f in v.link_faces}:f.material_index=material_index

for side in [o for o in parts if o.name=='FOUP_Side' or o.name.startswith('FOUP_Side.')]:
    if not side.get('thin_wall_v1'):
        for v in list(side.data.vertices)[:8]:v.co.x*=.4
        side['thin_wall_v1']=True
    if side.get('amber_detail_v1'):continue
    mesh=side.data;bm=bmesh.new();bm.from_mesh(mesh)
    grey=bpy.data.materials['FOUP_Door_Polymer']
    if grey.name not in [m.name for m in mesh.materials]:mesh.materials.append(grey)
    index=next(i for i,m in enumerate(mesh.materials) if m==grey)
    sign=1 if side.location.x>0 else -1
    # All additions stay inside the original 400 mm carrier width.
    for y in [-.135,-.09,-.045,.045,.09,.135]:
        detail_box(bm,side,(sign*.197,y,.178),(.005,.009,.25),0)
    for y in [-.065,.065]:detail_box(bm,side,(sign*.198,y,.195),(.003,.012,.09),index)
    for z in [.155,.235]:detail_box(bm,side,(sign*.198,0,z),(.003,.14,.012),index)
    bm.to_mesh(mesh);bm.free();mesh.update();side['amber_detail_v1']=True

for o in parts:
    assert tuple(v for row in o.matrix_local for v in row)==poses[o.name],o.name+' pivot moved'
for n,h in wafers.items():assert digest(bpy.data.objects[n])==h,n+' geometry changed'
assert len(wafers)==25
root['appearance']='Amber translucent polymer, graphite removable door, moulded ribs and recessed side grips; original envelope and interfaces preserved.'
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=root
output=os.path.join(BASE,'Assets','MOSFETInspection','Models','OHT','FOUP_300mm_Concept.fbx')
bpy.ops.export_scene.fbx(filepath=output,use_selection=True,object_types={'EMPTY','MESH'},axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BASE,'Blender','FOUP_300mm_Concept.blend'))
with open(os.path.join(BASE,'Tools','Backups','BeforeAmberFoup-20261023','blender-verification.json'),'w') as f:
    json.dump({'all_existing_local_poses_unchanged':True,'wafer_meshes_unchanged':25,'file':bpy.data.filepath,'objects':len(parts)},f,indent=2)
print('EXISTING_FOUP_AMBER_OK: original object poses and 25 wafer meshes preserved; saved existing blend and FBX')
