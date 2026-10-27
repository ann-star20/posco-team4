import bpy
import math
from mathutils import Vector


OUTPUT_BLEND = r"C:\Users\Administrator\Documents\Codex\UnityMOSFETFactory\Blender\efem_foop_model_v2.blend"
OUTPUT_PREVIEW = r"C:\Users\Administrator\Documents\Codex\UnityMOSFETFactory\Blender\efem_foop_model_v2_preview.png"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name, color, metallic=0.0, roughness=0.4, alpha=1.0, emission=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, alpha)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Alpha"].default_value = alpha
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 3.0
    if alpha < 1.0:
        mat.surface_render_method = "DITHERED"
    return mat


def empty(name, location=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.16
    obj.location = location
    if parent:
        obj.parent = parent
    return obj


def cube(name, location, dimensions, mat, parent=None, bevel=0.025):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("Edge_Bevel", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def cylinder(name, location, radius, depth, mat, parent=None, vertices=48, rotation=(0, 0, 0), bevel=0.015):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if bevel:
        modifier = obj.modifiers.new("Edge_Bevel", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def torus(name, location, major_radius, minor_radius, mat, parent=None, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=48,
        minor_segments=12,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def text_object(name, body, location, size, mat, parent=None, rotation=(math.radians(90), 0, 0)):
    bpy.ops.object.text_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.body = body
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.006
    obj.data.bevel_depth = 0.002
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def build_foop(index, x, mats, root):
    port = empty(f"LoadPort_{index:02d}", (x, -0.78, 0), root)
    cube(f"LoadPort_{index:02d}_Pedestal", (0, 0.02, 0.60), (1.12, 0.68, 1.00), mats["panel"], port, 0.035)
    cube(f"LoadPort_{index:02d}_Deck", (0, -0.20, 1.13), (1.18, 0.83, 0.10), mats["metal"], port, 0.025)
    cube(f"LoadPort_{index:02d}_DockPlate", (0, 0.25, 1.62), (0.98, 0.08, 0.88), mats["dark"], port, 0.025)
    cube(f"LoadPort_{index:02d}_DoorOpener", (0, 0.19, 1.62), (0.79, 0.08, 0.69), mats["metal"], port, 0.035)
    text_object(f"LoadPort_{index:02d}_Label", f"LP{index}", (0, -0.56, 0.87), 0.12, mats["dark"], port)

    foop = empty(f"FOUP_{index:02d}_ROOT", (0, -0.61, 1.54), port)
    cube(f"FOUP_{index:02d}_Body", (0, 0, 0.34), (0.92, 0.72, 0.83), mats["foop"], foop, 0.09)
    cube(f"FOUP_{index:02d}_TopHandle", (0, 0, 0.83), (0.40, 0.28, 0.12), mats["dark"], foop, 0.04)
    cube(f"FOUP_{index:02d}_FrontFrame", (0, -0.37, 0.34), (0.76, 0.06, 0.65), mats["dark"], foop, 0.045)
    door = cube(f"FOUP_{index:02d}_Door_ANIM", (0, -0.415, 0.34), (0.64, 0.045, 0.54), mats["door"], foop, 0.035)
    door["animation_role"] = "FOUP door retract and lower"
    for z in (-0.18, 0.0, 0.18):
        cube(f"FOUP_{index:02d}_DoorRib_{z:+.2f}", (0, -0.447, 0.34 + z), (0.52, 0.018, 0.035), mats["metal"], door, 0.008)
    cube(f"FOUP_{index:02d}_BottomCoupler", (0, 0, -0.10), (0.54, 0.43, 0.10), mats["dark"], foop, 0.025)
    return port


def build_robot(mats, root):
    robot = empty("Wafer_Robot_ROOT", (-0.55, 0.20, 1.22), root)
    cylinder("Robot_Base", (0, 0, 0.13), 0.31, 0.26, mats["dark"], robot)
    cylinder("Robot_Base_Collar", (0, 0, 0.31), 0.22, 0.14, mats["orange"], robot)

    joint_1 = empty("Robot_Joint_01_ANIM", (0, 0, 0.39), robot)
    cylinder("Robot_Joint_01_Housing", (0, 0, 0), 0.18, 0.18, mats["metal"], joint_1)
    arm_1 = cube("Robot_Arm_01", (0.48, 0, 0.03), (0.95, 0.20, 0.11), mats["orange"], joint_1, 0.06)
    cube("Robot_Arm_01_Top", (0.48, 0, 0.10), (0.72, 0.14, 0.05), mats["panel"], joint_1, 0.025)

    joint_2 = empty("Robot_Joint_02_ANIM", (0.95, 0, 0), joint_1)
    cylinder("Robot_Joint_02_Housing", (0, 0, 0.02), 0.15, 0.16, mats["dark"], joint_2)
    cube("Robot_Arm_02", (0.42, 0, 0.03), (0.84, 0.17, 0.09), mats["orange"], joint_2, 0.05)

    wrist = empty("Robot_Wrist_ANIM", (0.84, 0, 0.03), joint_2)
    cylinder("Robot_Wrist_Housing", (0, 0, 0), 0.11, 0.12, mats["metal"], wrist)
    effector = cube("Robot_EndEffector_ANIM", (0.36, 0, 0.01), (0.72, 0.12, 0.035), mats["metal"], wrist, 0.025)
    cube("Robot_EndEffector_Tip", (0.76, 0, 0.01), (0.15, 0.28, 0.025), mats["metal"], wrist, 0.025)
    wafer = cylinder("Robot_Wafer_Demo", (0.78, 0, 0.045), 0.15, 0.012, mats["wafer"], wrist, vertices=64)
    wafer["animation_role"] = "Reparent in Unity when picked or placed"
    return robot


def build_aligner(mats, root):
    aligner = empty("Wafer_Aligner_ROOT", (1.42, 0.23, 1.21), root)
    cube("Aligner_Base", (0, 0, 0.12), (0.72, 0.62, 0.24), mats["dark"], aligner, 0.06)
    cylinder("Aligner_Chuck_ANIM", (0, 0, 0.29), 0.22, 0.08, mats["metal"], aligner)
    cylinder("Aligner_Wafer_Demo", (0, 0, 0.35), 0.15, 0.012, mats["wafer"], aligner, vertices=64)
    cube("Aligner_NotchSensor", (0.24, -0.16, 0.35), (0.08, 0.10, 0.08), mats["orange"], aligner, 0.02)
    return aligner


def setup_camera_and_lighting(mats):
    floor = cube("Preview_Floor", (0, 0, -0.12), (8.0, 6.0, 0.12), mats["floor"], bevel=0.01)
    floor.hide_render = False

    bpy.ops.object.camera_add(location=(7.3, -8.8, 5.3))
    cam = bpy.context.object
    cam.name = "Preview_Camera"
    bpy.context.scene.camera = cam

    def point_camera(camera, target):
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()

    point_camera(cam, (0, -0.05, 1.55))
    cam.data.lens = 54

    for name, loc, energy, size, color in (
        ("Key_Area", (4.0, -4.0, 7.0), 1500, 5.0, (1.0, 0.93, 0.84)),
        ("Fill_Area", (-4.5, -1.0, 4.5), 1100, 4.0, (0.72, 0.85, 1.0)),
        ("Rim_Area", (1.0, 4.0, 5.5), 1300, 3.0, (0.8, 0.9, 1.0)),
    ):
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        point_camera(light, (0, 0, 1.5))


clear_scene()
scene = bpy.context.scene
scene.name = "EFEM_FOUP_Model_v1"
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1400
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.world.color = (0.025, 0.03, 0.04)

mats = {
    "white": material("EFEM_PowderCoat_White", (0.72, 0.77, 0.82), 0.15, 0.25),
    "panel": material("EFEM_Panel_Light", (0.9, 0.92, 0.94), 0.05, 0.3),
    "dark": material("EFEM_Graphite", (0.025, 0.035, 0.045), 0.4, 0.22),
    "metal": material("EFEM_Stainless", (0.34, 0.42, 0.48), 0.85, 0.2),
    "glass": material("EFEM_Cutaway_Glass", (0.55, 0.62, 0.66), 0.05, 0.12, 0.16),
    "foop": material("FOUP_Cleanroom_White", (0.78, 0.81, 0.83), 0.08, 0.3),
    "door": material("FOUP_Door_LightGray", (0.68, 0.71, 0.73), 0.42, 0.22),
    "wafer": material("Silicon_Wafer", (0.04, 0.14, 0.24), 0.72, 0.12),
    "orange": material("Robot_Cleanroom_White", (0.82, 0.85, 0.87), 0.18, 0.24),
    "green": material("Lamp_Green", (0.02, 0.35, 0.06), 0.0, 0.2, emission=(0.02, 0.9, 0.08)),
    "amber": material("Lamp_Amber", (0.55, 0.14, 0.01), 0.0, 0.2, emission=(1.0, 0.22, 0.01)),
    "red": material("Lamp_Red", (0.45, 0.01, 0.005), 0.0, 0.2, emission=(1.0, 0.02, 0.01)),
    "floor": material("Preview_Floor_Mat", (0.055, 0.065, 0.075), 0.1, 0.3),
}

root = empty("EFEM_ROOT")
static = empty("EFEM_BODY_STATIC", parent=root)

# Cabinet shell with a visible cutaway bay.
cube("EFEM_BasePlinth", (0, 0, 0.12), (4.9, 1.7, 0.24), mats["dark"], static, 0.05)
cube("EFEM_RearCabinet", (0, 0.45, 1.88), (4.7, 0.72, 3.35), mats["white"], static, 0.05)
cube("EFEM_TopHeader", (0, -0.08, 3.35), (4.7, 0.45, 0.42), mats["panel"], static, 0.04)
cube("EFEM_LeftColumn", (-2.2, -0.27, 1.88), (0.30, 0.50, 2.95), mats["panel"], static, 0.03)
cube("EFEM_RightColumn", (2.2, -0.27, 1.88), (0.30, 0.50, 2.95), mats["panel"], static, 0.03)
cube("EFEM_InternalDeck", (0, 0.02, 1.17), (4.12, 1.0, 0.10), mats["metal"], static, 0.02)
cube("EFEM_CutawayWindow", (0, -0.56, 2.30), (4.0, 0.035, 1.58), mats["glass"], static, 0.012)
for x in (-1.62, -0.54, 0.54, 1.62):
    cube(f"EFEM_LowerPanel_{x:+.2f}", (x, 0.44, 0.64), (1.0, 0.68, 0.86), mats["panel"], static, 0.025)

# Header details and status tower.
text_object("EFEM_Title", "300 mm EFEM", (0, -0.32, 3.39), 0.19, mats["dark"], static)
status = empty("EFEM_STATUS_TOWER", (2.08, -0.34, 3.48), root)
for z, name, mat_key in ((0.00, "Green", "green"), (0.11, "Amber", "amber"), (0.22, "Red", "red")):
    cylinder(f"StatusLamp_{name}", (0, 0, z), 0.055, 0.09, mats[mat_key], status)
cube("StatusLamp_Base", (0, 0, -0.08), (0.14, 0.14, 0.08), mats["dark"], status, 0.015)

for index, x in enumerate((-1.42, 0.0, 1.42), start=1):
    build_foop(index, x, mats, root)

build_robot(mats, root)
build_aligner(mats, root)

# Output handoff stage for the future process tool connection.
handoff = empty("Process_Handoff_ROOT", (2.03, 0.13, 1.34), root)
cube("Process_Handoff_Frame", (0, 0, 0.12), (0.42, 0.58, 0.24), mats["dark"], handoff, 0.04)
cube("Process_Handoff_Plate", (0, 0, 0.28), (0.34, 0.48, 0.06), mats["metal"], handoff, 0.02)

# Simple vent slots for scale and realism.
for i in range(22):
    x = -1.82 + i * 0.174
    cube(f"UpperVent_{i:02d}", (x, -0.322, 3.12), (0.09, 0.018, 0.025), mats["dark"], static, 0.008)

setup_camera_and_lighting(mats)

# Store project intent without adding animation data.
root["model_status"] = "MODELING_ONLY_NO_ANIMATION"
root["future_unity_motion"] = "FOUP dock, door retract, robot pick/place, aligner rotation"
scene.frame_start = 1
scene.frame_end = 240
scene.frame_set(1)

bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_BLEND)
scene.render.filepath = OUTPUT_PREVIEW
bpy.ops.render.render(write_still=True)
print(f"CREATED {OUTPUT_BLEND}")
print(f"PREVIEW {OUTPUT_PREVIEW}")
print(f"OBJECTS {len(bpy.data.objects)} ACTIONS {len(bpy.data.actions)}")
