import bpy,math,os
from mathutils import Vector
base=os.path.dirname(__file__)
bpy.ops.wm.open_mainfile(filepath=os.path.join(base,'AOI_Inspection_Line.blend'))
root=bpy.data.objects['MOSFET_Input_Buffer']
for o in list(root.children_recursive):bpy.data.objects.remove(o,do_unlink=True)
steel=bpy.data.materials['Aluminum'];white=bpy.data.materials['Powder_White'];dark=bpy.data.materials['Graphite'];yellow=bpy.data.materials['Safety_Yellow'];glass=bpy.data.materials['Smoked_Window'];green=bpy.data.materials['OK_Green'];red=bpy.data.materials['NG_Red']
m=bpy.data.materials['Green_Belt'];p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(.012,.016,.019,1);p.inputs['Roughness'].default_value=.6;m.name='Black_Conveyor_Belt'
def empty(n,loc=(0,0,0),par=root):
 o=bpy.data.objects.new(n,None);bpy.context.collection.objects.link(o);o.parent=par;o.location=loc;return o
def box(n,loc,dims,mat,par=root):
 bpy.ops.mesh.primitive_cube_add();o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat);q=o.modifiers.new('Edge','BEVEL');q.width=.006;q.segments=2;return o
def cyl(n,loc,r,d,mat,par=root):
 bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=r,depth=d);o=bpy.context.object;o.name=n;o.parent=par;o.location=loc;o.data.materials.append(mat);return o
# Framed machine with an open lower service bay.
for x in (-.48,.48):
 for y in (-.36,.36):
  box('Buffer_Extrusion_Post',(x,y,.87),(.035,.035,1.69),steel)
  cyl('Buffer_Foot',(x,y,.025),.04,.04,dark)
for z in (.18,.78,1.18,1.70):
 for y in (-.36,.36):box('Buffer_Frame_Crossbar',(0,y,z),(.99,.035,.035),steel)
 for x in (-.48,.48):box('Buffer_Frame_Sidebar',(x,0,z),(.035,.75,.035),steel)
box('Buffer_Lower_Front_Panel',(0,-.37,.46),(.91,.025,.54),white)
box('Buffer_Lower_Back_Panel',(0,.37,.46),(.91,.025,.54),white)
box('Buffer_Internal_Deck',(0,0,.79),(.92,.69,.035),steel)
# Open tapered hopper: large rectangular top narrows to the bottom outlet.
verts=[(-.43,-.31,1.67),(.43,-.31,1.67),(.43,.31,1.67),(-.43,.31,1.67),(-.15,-.10,1.22),(.15,-.10,1.22),(.15,.10,1.22),(-.15,.10,1.22)]
mesh=bpy.data.meshes.new('Hopper_Taper_Mesh');mesh.from_pydata(verts,[],[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);mesh.update()
o=bpy.data.objects.new('Open_Tapered_Hopper',mesh);bpy.context.collection.objects.link(o);o.parent=root;o.data.materials.append(steel);sol=o.modifiers.new('Metal_Sheet','SOLIDIFY');sol.thickness=.008
for y in (-.31,.31):box('Hopper_Top_Rim',(0,y,1.67),(.9,.022,.025),steel)
for x in (-.43,.43):box('Hopper_Top_Rim',(x,0,1.67),(.022,.65,.025),steel)
box('Hopper_Outlet',(0,0,1.19),(.32,.22,.08),dark)
cyl('Vibration_Drive',(0,0,1.06),.16,.17,dark)
box('Feeder_Mount',(0,0,.91),(.42,.35,.08),steel)
# Representative pile sits below the rim, preserving the visible open hopper.
for i in range(60):
 x=-.33+(i%10)*.072;y=-.23+((i//10)%6)*.09;z=1.55+(i%4)*.018
 b=box('Hopper_MOSFET',(x,y,z),(.065,.055,.022),dark);b.rotation_euler.z=(i*.91)%math.pi
# Inclined track descending toward the AOI infeed at matching belt height.
track=empty('Inclined_Alignment_Rail',(.43,0,1.07));track.rotation_euler.y=math.radians(14)
box('Feeder_Track_Base',(0,0,0),(.84,.15,.045),steel,track)
for y in (-.063,.063):box('Alignment_Guide',(0,y,.035),(.84,.016,.055),steel,track)
for j in range(5):box('Aligned_MOSFET',(-.29+j*.14,0,.041),(.065,.05,.018),dark,track)
gate=empty('Single_Part_Escapement',(.78,0,.98))
for y in (-.13,.13):box('Escapement_Cylinder',(0,y,0),(.10,.10,.15),steel,gate)
box('Escapement_Finger',(0,0,.01),(.022,.12,.04),yellow,gate)
box('Escapement_Sensor',(.08,-.10,.04),(.04,.035,.045),dark,gate)
box('Buffer_Output_Frame',(.91,0,.88),(.28,.25,.08),steel)
box('Buffer_Output_Belt',(.91,0,.925),(.28,.20,.01),m)
for y in (-.105,.105):box('Buffer_Output_Guide',(.91,y,.95),(.28,.02,.04),steel)
# Separate operator pedestal behind the outgoing feeder, clear of product flow.
box('Buffer_Control_Pedestal',(.58,.43,.65),(.30,.26,1.18),white)
box('Buffer_Control_Head',(.58,.43,1.35),(.34,.29,.32),white)
box('Buffer_HMI_Screen',(.58,.274,1.36),(.27,.012,.21),glass)
cyl('Buffer_Signal_Pole',(.58,.43,1.65),.016,.27,steel)
for j,mat in enumerate((green,yellow,red)):cyl('Buffer_Tower_Lamp',(.58,.43,1.82+j*.055),.032,.05,mat)
bpy.ops.wm.save_mainfile()
bpy.context.scene.render.filepath=os.path.join(base,'AOI_Inspection_Line_preview.png')
print('UPDATED_BUFFER_AND_BLACK_BELTS',bpy.data.filepath)
bpy.ops.render.render(write_still=True)
