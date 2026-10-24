"""Align stocker aperture, shutter and dock; check the carrier/fork pass-through envelope."""
import bpy,os,json,datetime
root=bpy.data.objects['Mini_Stocker']
base=os.path.dirname(bpy.data.filepath)
backup=os.path.join(base,'Mini_Stocker_BeforePortAlignment_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.blend')
bpy.ops.wm.save_as_mainfile(filepath=backup,copy=True)
for name,x in [('Port_Left_Jamb',.255),('Port_Right_Jamb',.885),('Port_Upper_Jamb',.57),('Port_Door_ANIM',.57)]:bpy.data.objects[name].location.x=x
upper=bpy.data.objects['Port_Upper_Jamb'];upper.dimensions.x=.70
shutter=bpy.data.objects['Transfer_Port_Shutter'];shutter.location.z=-.01;shutter.dimensions.z=.59
cover=bpy.data.collections['Stocker_Removable_Panels'];model=bpy.data.collections['Mini_Stocker_Asset']

def part(name,loc,dims,material,collection):
    o=bpy.data.objects.get(name)
    if not o:
        bpy.ops.mesh.primitive_cube_add(size=1);o=bpy.context.object;o.name=name
        for c in list(o.users_collection):c.objects.unlink(o)
        collection.objects.link(o);o.parent=bpy.data.objects['Body'];o.data.materials.append(material)
        mod=o.modifiers.new('Small_Edge_Radius','BEVEL');mod.width=.002;mod.segments=3;o.modifiers.new('Face_Normals','WEIGHTED_NORMAL')
    o.location=loc;o.dimensions=dims
    bpy.context.view_layer.objects.active=o;bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return o
part('Port_Right_Closure',(1.01,-.735,1.30),(.18,.035,.60),bpy.data.materials['ST_Warm_White'],cover)
part('Port_Lower_Jamb',(.57,-.735,1.0),(.70,.04,.04),bpy.data.materials['ST_Aluminium'],model)
bpy.context.view_layer.update()
from mathutils import Vector

def bounds(o):
    pts=[o.matrix_world@Vector(c) for c in o.bound_box]
    return [[f(p[i] for p in pts) for i in range(3)] for f in [min,max]]
L=bounds(bpy.data.objects['Port_Left_Jamb'])[1][0];R=bounds(bpy.data.objects['Port_Right_Jamb'])[0][0]
B=bounds(bpy.data.objects['Port_Lower_Jamb'])[1][2];T=bounds(upper)[0][2]
port=bpy.data.objects['FOUP_DockPoint'].matrix_world.translation
case=bpy.data.objects['FOUP_Example_01'];parts=[o for o in case.children_recursive if o.type=='MESH'];pts=[case.matrix_world.inverted()@(o.matrix_world@Vector(c)) for o in parts for c in o.bound_box]
caseMin=[min(p[i] for p in pts) for i in range(3)];caseMax=[max(p[i] for p in pts) for i in range(3)]
assert abs((L+R)*.5-port.x)<1e-5
assert L<port.x+caseMin[0] and port.x+caseMax[0]<R
assert B<port.z-.0505 and port.z+caseMax[2]<T
# Shutter travels upward behind the front panel; the complete carrier envelope is below its open bottom.
openBottom=bounds(shutter)[0][2]+bpy.data.objects['Port_Door_ANIM']['open_translation_local_m'][2]
assert openBottom>port.z+caseMax[2]
# Dock still matches the gantry attach point using the declared Z/X/Y axes.
e=bpy.data.objects['Elevator_Carriage'];x=bpy.data.objects['Horizontal_Slider'];f=bpy.data.objects['FOUP_Fork'];a=bpy.data.objects['FOUP_AttachPoint'];original=[o.location.copy() for o in [e,x,f]]
e.location.z=port.z-.04;x.location.x=port.x;f.location.y=port.y+.4-.32;bpy.context.view_layer.update()
assert (a.matrix_world.translation-port).length<1e-5
for o,p in zip([e,x,f],original):o.location=p
bpy.context.view_layer.update()
audit={'centre_x_m':round(port.x,4),'opening_width_m':round(R-L,4),'opening_height_m':round(T-B,4),'carrier_width_m':round(caseMax[0]-caseMin[0],4),'carrier_height_m':round(caseMax[2]-caseMin[2],4),'horizontal_carrier_clearance_each_m':round((R-L-(caseMax[0]-caseMin[0]))/2,4),'clearance_above_carrier_m':round(T-(port.z+caseMax[2]),4),'clearance_below_fork_m':round(port.z-.0505-B,4),'open_shutter_clearance_m':round(openBottom-(port.z+caseMax[2]),4),'note':'Static design-envelope check, not a full collision animation test.'}
p=os.path.join(base,'Mini_Stocker_6Slot_design.json');data=json.load(open(p,encoding='utf-8'));data['port_alignment_check']=audit;json.dump(data,open(p,'w',encoding='utf-8'),indent=2)
root['port_alignment']='Aperture and shutter centred at X=0.57 m, same as dock and gantry. Carrier/fork clearance checked.'
bpy.ops.object.select_all(action='DESELECT');root.select_set(True);bpy.context.view_layer.objects.active=root
bpy.context.window.scene=bpy.data.scenes['Mini_Stocker_Exterior']
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
print('PORT_ALIGNMENT_OK',json.dumps(audit),'BACKUP',backup)
