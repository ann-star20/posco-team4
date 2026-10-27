"""Absolute exterior positions; safe to reapply without moving the animation anchors."""
import bpy, os

def update_exterior():
    for name in ['HMI_Bezel','HMI_Screen']:
        bpy.data.objects[name].location.z=1.80
    for name in ['Emergency_Stop','Emergency_Stop_Collar','Control_Selector']:
        bpy.data.objects[name].location.z=1.28
    for o in list(bpy.data.objects):
        if o.name.startswith('Observation_Window') or o.name.startswith('Port_Status_Panel_'):
            bpy.data.objects.remove(o,do_unlink=True)
    def box(name,location,size,parent,material):
        bpy.ops.mesh.primitive_cube_add()
        o=bpy.context.view_layer.objects.active;o.name=name;o.parent=parent;o.location=location;o.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        o.data.materials.append(material)
        bevel=o.modifiers.new('Edge_Radius','BEVEL');bevel.width=.006;bevel.segments=3
        return o
    for i,x in enumerate([-2,-1.05,-.1,.85],1):
        box('Port_Status_Panel_%02d'%i,(x-.0025,-.6425,2.0),(.66,.025,.12),bpy.data.objects['Main_Body'],bpy.data.materials['Dark_Window'])
    tower=bpy.data.objects['Signal_Tower'];tower.location=(1.72,-.35,2.98)
    if 'Tower_Roof_Base' not in bpy.data.objects:
        box('Tower_Roof_Base',(0,0,-.17),(.14,.14,.02),tower,bpy.data.materials['Steel'])
        bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.019,depth=.15)
        stem=bpy.context.view_layer.objects.active;stem.name='Tower_Roof_Stem';stem.parent=tower;stem.location=(0,0,-.11);stem.data.materials.append(bpy.data.materials['Steel'])
    bpy.context.view_layer.update()
    stop=bpy.data.objects['Emergency_Stop_Collar'];shelf=bpy.data.objects['Console_Shelf'];screen=bpy.data.objects['HMI_Bezel']
    assert stop.location.z-stop.dimensions.y/2 > shelf.location.z+shelf.dimensions.z/2+.10
    assert screen.location.z-screen.dimensions.z/2 > stop.location.z+stop.dimensions.y/2+.08
    assert len([o for o in bpy.data.objects if o.name.startswith('Port_Status_Panel_')])==4
    print('ION_EXTERIOR_CHECK_OK: monitor Z=1.80; controls Z=1.28; 4 LED backplates; roof-mounted tower')

def export_model():
    root=bpy.data.objects['Ion_Implanter']
    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
    bpy.ops.object.select_all(action='DESELECT')
    for o in [root]+list(root.children_recursive):
        if not o.name.startswith('Preview_'):o.select_set(True)
    bpy.context.view_layer.objects.active=root
    path=os.path.join(os.path.dirname(bpy.data.filepath),'..','Assets','MOSFETInspection','Models','FabEquipment','Ion_Implanter_Animated.fbx')
    bpy.ops.export_scene.fbx(filepath=path,use_selection=True,object_types={'EMPTY','MESH'},apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=False,add_leaf_bones=False,use_triangles=True)

update_exterior()
