"""Export the active standalone ellipsometer; retain editable text in the source file."""
import bpy, os, json

root=bpy.data.objects['Ellipsometer_System']
out=os.path.join(os.path.dirname(bpy.data.filepath),'..','Assets','MOSFETInspection','Models','FabEquipment')
items=[root]+list(root.children_recursive)
bpy.ops.object.select_all(action='DESELECT')
copies=[]
for obj in items:
    if obj.type=='FONT':
        copy=obj.copy();copy.data=obj.data.copy();bpy.context.collection.objects.link(copy)
        copy.name=obj.name+'_Export';copies.append(copy)
        bpy.context.view_layer.objects.active=copy;copy.select_set(True)
        bpy.ops.object.convert(target='MESH');copy.select_set(False)
records={}
try:
    for obj in items+copies:
        if obj.type=='FONT':continue
        obj.select_set(True)
        if obj.type=='MESH':
            for mat in obj.data.materials:
                if not mat:continue
                node=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
                if node:records[mat.name]={'name':mat.name,'color':list(node.inputs['Base Color'].default_value),'metallic':node.inputs['Metallic'].default_value,'roughness':node.inputs['Roughness'].default_value}
    bpy.context.view_layer.objects.active=root
    bpy.ops.export_scene.fbx(filepath=os.path.join(out,'Ellipsometer_System.fbx'),use_selection=True,object_types={'EMPTY','MESH'},apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False,use_triangles=True)
    with open(os.path.join(out,'Ellipsometer_materials.json'),'w',encoding='utf-8') as stream:json.dump({'items':list(records.values())},stream)
finally:
    for obj in copies:bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT');root.select_set(True);bpy.context.view_layer.objects.active=root
print('ELLIPSOMETER_EXPORT_OK')
