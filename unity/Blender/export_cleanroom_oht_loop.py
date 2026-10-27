import bpy,os,json
BASE=r'C:/Users/Administrator/Documents/Codex/UnityMOSFETFactory'
root=bpy.data.objects['OHT_Cleanroom_Loop'];scene=bpy.context.scene
out=os.path.join(BASE,'Assets','MOSFETInspection','Models','OHTLoop')
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
