import bpy,os,json
base=os.path.dirname(__file__)
out=os.path.join(os.path.dirname(base),'Assets','MOSFETInspection','Models','FabEquipment')
os.makedirs(out,exist_ok=True)
items=[('EFEM','EFEM_ROOT'),('Oxidation_Furnace','Oxidation_Furnace_ROOT'),('Ion_Implanter','Ion_Implanter'),('Molding_Machine','Molding_Machine_ROOT'),('AOI_Inspection_Line','AOI_Inspection_Line')]
report={}
for filename,rootname in items:
 bpy.ops.wm.open_mainfile(filepath=os.path.join(base,filename+'.blend'))
 root=bpy.data.objects[rootname]
 objects=[root]+list(root.children_recursive)
 # Preview floors have no role in equipment exports.
 objects=[o for o in objects if not o.name.startswith('Preview_')]
 bpy.ops.object.select_all(action='DESELECT')
 mats={}
 for obj in objects:
  obj.hide_set(False);obj.hide_viewport=False
  if obj.type=='MESH':
   for mat in obj.data.materials:
    if not mat:continue
    node=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None) if mat.use_nodes else None
    if node:
     mats[mat.name]={'color':list(node.inputs['Base Color'].default_value),'metallic':node.inputs['Metallic'].default_value,'roughness':node.inputs['Roughness'].default_value}
  obj.select_set(True)
 root.location=(0,0,0)
 bpy.context.view_layer.objects.active=root
 # Hidden FOUPs remain absent from the initial EFEM presentation.
 if filename=='EFEM':
  for obj in objects:
   if obj.name.startswith('FOUP_'):obj.select_set(False)
 bpy.ops.export_scene.fbx(filepath=os.path.join(out,filename+'.fbx'),use_selection=True,object_types={'EMPTY','MESH','OTHER'},apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False)
 report[filename]=mats
 print('EXPORTED',filename,len(objects))
with open(os.path.join(out,'materials.json'),'w',encoding='utf-8') as f:json.dump(report,f)
