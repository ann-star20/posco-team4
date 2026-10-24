"""Export only the stocker and separate example carriers, without preview ground/lights."""
import bpy,os,json
root=bpy.data.objects['Mini_Stocker'];scene=bpy.context.scene
out=r'C:/Users/Administrator/Documents/Codex/UnityMOSFETFactory/Assets/MOSFETInspection/Models/Stocker'
os.makedirs(out,exist_ok=True)
for name,loc in [('Stocker_Frame_Origin',(0,0,0)),('Stocker_Frame_X',(1,0,0)),('Stocker_Frame_Up',(0,0,1)),('Stocker_Frame_Front',(0,-1,0))]:
    if not bpy.data.objects.get(name):
        o=bpy.data.objects.new(name,None);bpy.data.collections['Mini_Stocker_Asset'].objects.link(o);o.parent=root;o.location=loc;o.empty_display_size=.03
items=[root]+list(root.children_recursive)
for name in ['FOUP_Example_01','FOUP_Example_02','FOUP_Example_03']:
    o=bpy.data.objects[name];items+=[o]+list(o.children_recursive)
copies=[];materials={}
try:
    bpy.ops.object.select_all(action='DESELECT')
    for obj in items:
        if obj.type=='FONT':
            copy=obj.copy();copy.data=obj.data.copy();scene.collection.objects.link(copy);copy.name=obj.name+'_Export'
            bpy.context.view_layer.objects.active=copy;copy.select_set(True);bpy.ops.object.convert(target='MESH');copy.select_set(False);copies.append(copy)
    for obj in items+copies:
        if obj.type=='FONT':continue
        obj.select_set(True)
        if obj.type=='MESH':
            for mat in obj.data.materials:
                if not mat:continue
                node=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
                materials[mat.name]={'name':mat.name,'color':list(node.inputs['Base Color'].default_value),'metallic':node.inputs['Metallic'].default_value,'roughness':node.inputs['Roughness'].default_value}
    bpy.context.view_layer.objects.active=root
    bpy.ops.export_scene.fbx(filepath=os.path.join(out,'Mini_Stocker_6Slot.fbx'),use_selection=True,object_types={'EMPTY','MESH'},apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False,use_triangles=True)
    json.dump({'items':list(materials.values())},open(os.path.join(out,'Stocker_materials.json'),'w',encoding='utf-8'),indent=2)
finally:
    for o in copies:bpy.data.objects.remove(o,do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT');root.select_set(True);bpy.context.view_layer.objects.active=root
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
print('STOCKER_EXPORT_OK',out,'objects',len(items),'materials',len(materials))
