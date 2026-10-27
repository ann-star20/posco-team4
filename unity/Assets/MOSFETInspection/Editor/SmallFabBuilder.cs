#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

public static class SmallFabBuilder
{
    [InitializeOnLoadMethod]
    static void BuildRequested()
    {
        if (!File.Exists("BuildSmallFab.once")) return;
        EditorApplication.delayCall += () =>
        {
            if (!File.Exists("BuildSmallFab.once")) return;
            var current = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if (current.isDirty && (string.IsNullOrEmpty(current.path) || !EditorSceneManager.SaveScene(current)))
            { Debug.LogError("Small fab build waiting: save the current scene first."); return; }
            File.Delete("BuildSmallFab.once");
            try { Build(); } catch (Exception e) { Debug.LogException(e); File.WriteAllText("SmallFabBuild.result",e.ToString()); }
        };
    }
    const string Base = "Assets/MOSFETInspection/";
    const string Models = Base + "Models/FabEquipment/";
    const string Output = Base + "Scenes/MOSFETSmallFab_Corrected.unity";
    [Serializable] class Record { public string equipment; public string name; public float[] color; public float metallic; public float roughness; }
    [Serializable] class Records { public Record[] items; }
    static Transform shell;
    static Material Mat(string name, Color c, float metal = 0, float smooth = .45f)
    {
        var folder = Base + "Materials/SmallFab";
        Directory.CreateDirectory(folder);
        var path = folder + "/" + name + ".mat";
        var m = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (!m) { m = new Material(Shader.Find("HDRP/Lit")); AssetDatabase.CreateAsset(m, path); }
        m.SetColor("_BaseColor", c); m.SetFloat("_Metallic", metal); m.SetFloat("_Smoothness", smooth);
        EditorUtility.SetDirty(m); return m;
    }
    static GameObject Box(string name, Vector3 position, Vector3 size, Material m, Transform parent = null)
    {
        var o = GameObject.CreatePrimitive(PrimitiveType.Cube); o.name = name;
        o.transform.SetParent(parent ? parent : shell, false); o.transform.localPosition = position;
        o.transform.localScale = size; o.GetComponent<Renderer>().sharedMaterial = m; return o;
    }
    static Bounds BoundsOf(GameObject o)
    {
        var renderers = o.GetComponentsInChildren<Renderer>();
        if (renderers.Length == 0) throw new InvalidOperationException("No model geometry: " + o.name);
        var b = renderers[0].bounds; foreach (var r in renderers) b.Encapsulate(r.bounds); return b;
    }
    static GameObject Place(string name, float x, float frontZ, Record[] records, float yaw = 0, bool frontRow = false, float scale = 1f)
    {
        var asset = AssetDatabase.LoadAssetAtPath<GameObject>(Models + name + ".fbx");
        if (!asset) throw new InvalidOperationException("Missing model " + name);
        var o = (GameObject)PrefabUtility.InstantiatePrefab(asset); o.name = name;
        o.transform.rotation = Quaternion.Euler(0,yaw,0) * o.transform.rotation;
        o.transform.localScale *= scale;
        var bounds = BoundsOf(o);
        // Unity FBX import reverses the Blender front direction; rear faces -Z, front row +Z.
        o.transform.position += new Vector3(x - bounds.center.x, -bounds.min.y, frontZ - (frontRow ? bounds.max.z : bounds.min.z));
        foreach (var renderer in o.GetComponentsInChildren<Renderer>())
        {
            renderer.sharedMaterials = renderer.sharedMaterials.Select(original =>
            {
                var record = records.FirstOrDefault(r => r.equipment == name && original && r.name == original.name);
                if (record == null) return Mat("EquipmentFallback", new Color(.65f,.69f,.72f), .25f);
                var c = record.color;
                return Mat(name + "_" + record.name, new Color(c[0],c[1],c[2],1).gamma, record.metallic, 1-record.roughness);
            }).ToArray();
        }
        bounds = BoundsOf(o);
        if (Mathf.Abs(bounds.min.y) > .005f)
            throw new InvalidOperationException("Equipment not grounded: " + name + " minY=" + bounds.min.y);
        if (name == "EFEM" && (bounds.size.y < 3.4f || bounds.size.y > 4f))
            throw new InvalidOperationException("EFEM import orientation is incorrect: " + bounds.size);
        if (name == "Ion_Implanter" && (bounds.size.y < 3.5f || bounds.size.y > 3.9f))
            throw new InvalidOperationException("Implanter import orientation is incorrect: " + bounds.size);
        if (bounds.min.x < -7.85f || bounds.max.x > 7.85f || bounds.max.z > 5.85f || bounds.min.z < -5.85f)
            throw new InvalidOperationException("Equipment exceeds room: " + name + " " + bounds);
        Debug.Log("FAB_EQUIPMENT_BOUNDS " + name + " " + bounds);
        return o;
    }
    [MenuItem("MOSFET Factory/Build Small Cleanroom Fab")]
    public static void Build()
    {
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        var records = JsonUtility.FromJson<Records>(File.ReadAllText(Models + "material-records.json")).items;
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        shell = new GameObject("SMALL_FAB_16x12m").transform;
        var floor = Mat("CleanroomFloor",new Color(.56f,.66f,.69f),.12f,.6f);
        var wall = Mat("CleanroomWhite",new Color(.88f,.91f,.92f));
        var trim = Mat("PanelTrim",new Color(.46f,.54f,.59f),.65f);
        var blue = Mat("WaferZoneBlue",new Color(.03f,.36f,.65f));
        var green = Mat("InspectionZoneGreen",new Color(.025f,.44f,.22f));
        Box("Floor_16x12m",new Vector3(0,-.10f,0),new Vector3(16,.20f,12),floor);
        Box("Rear_Wall",new Vector3(0,2.25f,6),new Vector3(16,4.5f,.12f),wall);
        Box("Left_Wall",new Vector3(-8,2.25f,0),new Vector3(.12f,4.5f,12),wall);
        // Front and right walls are grouped for an unobstructed presentation cutaway.
        var cutaway = new GameObject("Front_Right_Walls_Toggle"); cutaway.transform.SetParent(shell);
        Box("Front_Wall",new Vector3(0,2.25f,-6),new Vector3(16,4.5f,.12f),wall,cutaway.transform);
        Box("Right_Wall",new Vector3(8,2.25f,0),new Vector3(.12f,4.5f,12),wall,cutaway.transform);
        cutaway.SetActive(false);
        for (int i=0;i<16;i++) Box("Rear_Panel_Joint",new Vector3(-7.5f+i,2.25f,5.93f),new Vector3(.012f,4.35f,.01f),trim);
        var ceiling = new GameObject("Ceiling_FFU_Toggle"); ceiling.transform.SetParent(shell);
        for (int x=-7;x<=7;x+=2) for (int z=-5;z<=5;z+=2)
        {
            Box("Ceiling_Filter_Panel",new Vector3(x,4.47f,z),new Vector3(1.94f,.06f,1.94f),wall,ceiling.transform);
            Box("FFU_Filter",new Vector3(x,4.42f,z),new Vector3(.95f,.035f,.60f),trim,ceiling.transform);
        }
        ceiling.SetActive(false);
        foreach (var z in new[]{-3.05f,-.55f}) Box("Central_Aisle_Edge",new Vector3(0,.006f,z),new Vector3(15,.012f,.055f),blue);
        Box("Inspection_Zone_Edge",new Vector3(0,.007f,-5.65f),new Vector3(15,.012f,.055f),green);
        // Five individually editable equipment instances at their original scale.
        Place("EFEM",-4.75f,-.35f,records,180);
        Place("Oxidation_Furnace",-.80f,-.35f,records,180);
        Place("Ion_Implanter",3.60f,-.35f,records,180);
        Place("Molding_Machine",-4.45f,-3.05f,records,0,true);
        Place("AOI_Inspection_Line",3.25f,-3.05f,records,0,true,1.25f);
        var volume = new GameObject("Cleanroom_Global_Volume").AddComponent<Volume>();
        volume.isGlobal=true; var profile=ScriptableObject.CreateInstance<VolumeProfile>();
        var exposure=profile.Add<Exposure>(); exposure.mode.Override(ExposureMode.Fixed); exposure.fixedExposure.Override(6f);
        var sky=profile.Add<GradientSky>(); sky.top.Override(new Color(.40f,.50f,.65f));sky.middle.Override(new Color(.65f,.70f,.75f));sky.bottom.Override(new Color(.35f,.40f,.45f));
        var visual=profile.Add<VisualEnvironment>();visual.skyType.Override((int)SkyType.Gradient);
        var profilePath=Base+"Materials/SmallFab/CleanroomVolume.asset";
        if (AssetDatabase.LoadAssetAtPath<VolumeProfile>(profilePath)) AssetDatabase.DeleteAsset(profilePath);
        AssetDatabase.CreateAsset(profile,profilePath);
        foreach(var component in profile.components) AssetDatabase.AddObjectToAsset(component,profile);
        volume.sharedProfile=profile;
        var lamp=new GameObject("Cleanroom_KeyLight").AddComponent<Light>();lamp.type=LightType.Directional;lamp.gameObject.AddComponent<HDAdditionalLightData>();lamp.lightUnit=LightUnit.Lux;lamp.intensity=1100;lamp.shadows=LightShadows.Soft;lamp.transform.rotation=Quaternion.Euler(55,-25,0);
        var fill=new GameObject("Cleanroom_FillLight").AddComponent<Light>();fill.type=LightType.Directional;fill.gameObject.AddComponent<HDAdditionalLightData>();fill.lightUnit=LightUnit.Lux;fill.intensity=700;fill.transform.rotation=Quaternion.Euler(65,145,0);
        var softFill=new GameObject("Cleanroom_FrontFill").AddComponent<Light>();
        softFill.type=LightType.Directional;softFill.gameObject.AddComponent<HDAdditionalLightData>();softFill.lightUnit=LightUnit.Lux;softFill.intensity=400;softFill.color=Color.white;softFill.transform.rotation=Quaternion.Euler(40,35,0);
        var camera=new GameObject("FAB_OVERVIEW_CAMERA").AddComponent<Camera>();
        camera.transform.position=new Vector3(15,13,-17);camera.transform.LookAt(new Vector3(0,.7f,0));camera.fieldOfView=48;
        camera.nearClipPlane=.1f;camera.farClipPlane=100;
        camera.gameObject.AddComponent<HDAdditionalCameraData>();
        EditorSceneManager.SaveScene(scene,Output);AssetDatabase.SaveAssets();
        File.WriteAllText("SmallFabBuild.result","SMALL_FAB_BUILD_OK\n"+Output);
        Debug.Log("SMALL_FAB_BUILD_OK " + Output);
        Selection.activeGameObject = shell.gameObject;
        if (SceneView.lastActiveSceneView != null)
            SceneView.lastActiveSceneView.LookAt(new Vector3(0,1,0),camera.transform.rotation,18);
    }
}
#endif
