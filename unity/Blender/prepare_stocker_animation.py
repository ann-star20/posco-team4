import bpy,datetime,json,os
from mathutils import Vector
base=r'C:/Users/Administrator/Documents/Codex/UnityMOSFETFactory/Blender'
assert bpy.data.filepath.replace('\\','/').endswith('/Mini_Stocker_6Slot.blend')
bpy.ops.wm.save_as_mainfile(filepath=base+'/Before_Stocker_Animation_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.blend',copy=True)
bpy.data.objects['Moving_X_Beam'].location.z=-.05
bpy.data.objects['X_Linear_Guide'].location.z=-.015
bpy.data.objects['X_Carriage_Block'].location.z=-.055
bpy.data.objects['FOUP_Fork'].location.y=-.18
bpy.context.view_layer.update()
# The carrier and empty fork must fit behind the front panel during X/Z travel.
root=bpy.data.objects['Mini_Stocker']
attach=bpy.data.objects['FOUP_AttachPoint'];fork=bpy.data.objects['FOUP_Fork']
points=[o.matrix_world@Vector(v) for o in fork.children_recursive if o.type=='MESH' for v in o.bound_box]
assert min(v.y for v in points)>-.6925+.01
assert abs(attach.matrix_world.translation.y+.26)<1e-5
for n in ['Moving_X_Beam','X_Linear_Guide','X_Carriage_Block']:
 o=bpy.data.objects[n];highest=max((o.matrix_world@Vector(v)).z for v in o.bound_box)
 assert highest<attach.matrix_world.translation.z-.01,(n,highest)
root['animation_note']='Unity StockerCycle drives Z elevator, X slider, telescopic Y fork and I/O shutter; stocker reserves an empty return slot until OHT returns.'
root['clear_lane_design_y_m']=-.26
file=base+'/Mini_Stocker_6Slot_design.json';data=json.load(open(file,encoding='utf-8-sig'))
data['animation_clear_lane_y_m']=-.26;data['fork_payload_underbody_clearance_m']=.0155
data['note']='Six-slot stocker with Unity-controlled dispatch/receive, OHT handoff and reserved return slot. Internal mechanism is a simplified presentation model.'
json.dump(data,open(file,'w',encoding='utf-8'),indent=2)
bpy.context.window.scene=bpy.data.scenes['Mini_Stocker_Exterior']
bpy.ops.wm.save_as_mainfile(filepath=base+'/Mini_Stocker_6Slot.blend')
exec(compile(open(base+'/export_mini_stocker.py',encoding='utf-8-sig').read(),'export_mini_stocker.py','exec'))
print('STOCKER_ANIMATION_GEOMETRY_READY; clear lane -0.26m; fork and payload support clearances checked')
