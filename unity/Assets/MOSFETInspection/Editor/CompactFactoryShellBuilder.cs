#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

public static class CompactFactoryShellBuilder
{
    private const string SourceScene =
        "Assets/UnityFactorySceneHDRP/Scene_Factory/FactorySceneSample.unity";
    private const string OutputScene =
        "Assets/MOSFETInspection/Scenes/MOSFETCompactFactory.unity";
    private const string MaterialFolder =
        "Assets/MOSFETInspection/Materials/CompactFactory";
    private const string GeneratedRootName = "MOSFET_COMPACT_FACTORY";
    private const string BuildRequestFile = "BuildCompactFactory.once";

    [InitializeOnLoadMethod]
    private static void RunRequestedBuildOnce()
    {
        var requestPath = Path.Combine(Directory.GetCurrentDirectory(), BuildRequestFile);
        if (!File.Exists(requestPath))
            return;

        File.Delete(requestPath);
        EditorApplication.delayCall += () =>
        {
            try
            {
                BuildCompactFactory();
            }
            catch (Exception exception)
            {
                Debug.LogException(exception);
            }
        };
    }

    [MenuItem("MOSFET Factory/Build Compact Factory Shell")]
    public static void BuildCompactFactory()
    {
        var scene = EditorSceneManager.OpenScene(SourceScene, OpenSceneMode.Single);
        Directory.CreateDirectory(Path.GetDirectoryName(OutputScene) ??
                                  "Assets/MOSFETInspection/Scenes");
        if (!EditorSceneManager.SaveScene(scene, OutputScene, true))
            throw new InvalidOperationException("Could not create the compact factory scene.");

        scene = SceneManager.GetActiveScene();
        HideSampleProductionObjects(scene);

        var oldRoot = GameObject.Find(GeneratedRootName);
        if (oldRoot != null)
            UnityEngine.Object.DestroyImmediate(oldRoot);

        var anchor = FindPrimaryLine(scene);
        var root = new GameObject(GeneratedRootName);
        root.transform.SetPositionAndRotation(anchor.position, anchor.rotation);

        var floor = GetOrCreateMaterial("FactoryFloor", new Color(0.12f, 0.14f, 0.15f), 0.15f, 0.42f);
        var wall = GetOrCreateMaterial("FactoryWall", new Color(0.33f, 0.36f, 0.38f), 0.1f, 0.35f);
        var steel = GetOrCreateMaterial("StructuralSteel", new Color(0.08f, 0.1f, 0.12f), 0.65f, 0.48f);
        var bay = GetOrCreateMaterial("LineBay", new Color(0.16f, 0.18f, 0.19f), 0.05f, 0.28f);
        var green = GetOrCreateMaterial("SafetyGreen", new Color(0.015f, 0.24f, 0.105f), 0f, 0.2f);
        var yellow = GetOrCreateMaterial("WalkwayYellow", new Color(0.86f, 0.55f, 0.03f), 0f, 0.25f);
        var whiteLight = GetOrCreateMaterial("CeilingLight", new Color(0.82f, 0.9f, 0.95f), 0f, 0.75f, true);

        CreateCube(root.transform, "Compact Factory Floor", new Vector3(0f, -0.1f, 0f),
            new Vector3(22f, 0.2f, 16f), floor);
        CreateCube(root.transform, "Back Wall", new Vector3(0f, 3.8f, 8f),
            new Vector3(22f, 7.6f, 0.22f), wall);
        CreateCube(root.transform, "Left Wall", new Vector3(-11f, 3.8f, 0f),
            new Vector3(0.22f, 7.6f, 16f), wall);
        CreateCube(root.transform, "Right Wall", new Vector3(11f, 3.8f, 0f),
            new Vector3(0.22f, 7.6f, 16f), wall);

        AddStructure(root.transform, steel, whiteLight);
        AddLineBays(root.transform, bay, green);
        AddFrontWalkway(root.transform, yellow);
        AddUtilityArea(root.transform, steel, wall);
        AddOverviewCamera(scene, root.transform);

        EditorSceneManager.MarkSceneDirty(scene);
        if (!EditorSceneManager.SaveScene(scene, OutputScene))
            throw new InvalidOperationException("Could not save the compact factory scene.");

        Selection.activeGameObject = root;
        Debug.Log("MOSFET_COMPACT_FACTORY_BUILD_OK\n" +
                  "Three empty production bays are ready for equipment placement.\n" +
                  $"Saved scene: {OutputScene}");
    }

    private static Transform FindPrimaryLine(Scene scene)
    {
        var line = scene.GetRootGameObjects()
            .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
            .FirstOrDefault(item => item.name == "Line_01");
        if (line == null)
            throw new InvalidOperationException("Unity Factory Line_01 anchor was not found.");
        return line;
    }

    private static void HideSampleProductionObjects(Scene scene)
    {
        var objects = scene.GetRootGameObjects()
            .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
            .Where(item => System.Text.RegularExpressions.Regex.IsMatch(item.name, @"^Line_\d{2}$") ||
                           string.Equals(item.name, "Worker", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        foreach (var item in objects)
            item.gameObject.SetActive(false);
    }

    private static void AddStructure(Transform root, Material steel, Material lightMaterial)
    {
        foreach (var x in new[] { -10.5f, -3.5f, 3.5f, 10.5f })
        {
            CreateCube(root, $"Column L {x:0.0}", new Vector3(x, 3.6f, -7.5f),
                new Vector3(0.22f, 7.2f, 0.22f), steel);
            CreateCube(root, $"Column R {x:0.0}", new Vector3(x, 3.6f, 7.5f),
                new Vector3(0.22f, 7.2f, 0.22f), steel);
            CreateCube(root, $"Roof Beam {x:0.0}", new Vector3(x, 7.05f, 0f),
                new Vector3(0.18f, 0.22f, 15f), steel);
        }

        foreach (var z in new[] { -5.6f, -1.9f, 1.9f, 5.6f })
        {
            CreateCube(root, $"Ceiling Light {z:0.0}", new Vector3(0f, 6.65f, z),
                new Vector3(17f, 0.06f, 0.16f), lightMaterial);
            var lightObject = new GameObject($"Work Light {z:0.0}");
            lightObject.transform.SetParent(root, false);
            lightObject.transform.localPosition = new Vector3(0f, 6.3f, z);
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = new Color(0.84f, 0.91f, 1f);
            light.intensity = 900f;
            light.range = 11f;
            light.shadows = LightShadows.Soft;
        }
    }

    private static void AddLineBays(Transform root, Material bay, Material green)
    {
        const float spacing = 4.2f;
        for (var i = 0; i < 3; i++)
        {
            var z = -spacing + spacing * i;
            var bayRoot = new GameObject($"MOSFET_LINE_{i + 1:00}_BAY");
            bayRoot.transform.SetParent(root, false);
            bayRoot.transform.localPosition = new Vector3(0f, 0f, z);

            CreateCube(bayRoot.transform, "Equipment Placement Floor", new Vector3(0f, 0.015f, 0f),
                new Vector3(18f, 0.03f, 3.35f), bay);
            AddRectangle(bayRoot.transform, new Vector2(18.3f, 3.65f), green);
            CreateLabel(bayRoot.transform, $"MOSFET LINE {i + 1:00}",
                new Vector3(-8.1f, 0.035f, -1.35f), Quaternion.Euler(90f, 0f, 0f));
        }
    }

    private static void AddRectangle(Transform parent, Vector2 size, Material material)
    {
        const float width = 0.08f;
        const float height = 0.025f;
        var halfX = size.x * 0.5f;
        var halfZ = size.y * 0.5f;
        CreateCube(parent, "Front Safety Stripe", new Vector3(0f, height, -halfZ),
            new Vector3(size.x, height, width), material);
        CreateCube(parent, "Back Safety Stripe", new Vector3(0f, height, halfZ),
            new Vector3(size.x, height, width), material);
        CreateCube(parent, "Left Safety Stripe", new Vector3(-halfX, height, 0f),
            new Vector3(width, height, size.y), material);
        CreateCube(parent, "Right Safety Stripe", new Vector3(halfX, height, 0f),
            new Vector3(width, height, size.y), material);
    }

    private static void AddFrontWalkway(Transform root, Material yellow)
    {
        CreateCube(root, "Front Walkway Line", new Vector3(0f, 0.025f, -6.85f),
            new Vector3(20f, 0.03f, 0.1f), yellow);
        for (var x = -9f; x <= 9f; x += 1.5f)
            CreateCube(root, $"Walkway Dash {x:0.0}", new Vector3(x, 0.026f, -5.95f),
                new Vector3(0.7f, 0.032f, 0.08f), yellow);
    }

    private static void AddUtilityArea(Transform root, Material steel, Material wall)
    {
        CreateCube(root, "Jetson Control Cabinet Placeholder", new Vector3(9.45f, 1.15f, -6.9f),
            new Vector3(1.7f, 2.3f, 1.25f), wall);
        CreateCube(root, "Control Cabinet Plinth", new Vector3(9.45f, 0.12f, -6.9f),
            new Vector3(1.9f, 0.24f, 1.45f), steel);
        CreateLabel(root, "JETSON CONTROL", new Vector3(9.44f, 1.55f, -7.54f),
            Quaternion.Euler(0f, 180f, 0f));
    }

    private static void AddOverviewCamera(Scene scene, Transform root)
    {
        foreach (var existingCamera in scene.GetRootGameObjects()
                     .SelectMany(item => item.GetComponentsInChildren<Camera>(true)))
            existingCamera.enabled = false;

        var cameraObject = new GameObject("COMPACT_FACTORY_OVERVIEW_CAMERA");
        cameraObject.transform.SetParent(root, false);
        cameraObject.transform.localPosition = new Vector3(15.5f, 11.5f, -18.5f);
        cameraObject.transform.LookAt(root.TransformPoint(new Vector3(0f, 0.8f, 0f)));
        var camera = cameraObject.AddComponent<Camera>();
        camera.enabled = true;
        camera.fieldOfView = 48f;

        var sceneView = SceneView.lastActiveSceneView;
        if (sceneView != null)
            sceneView.LookAt(root.TransformPoint(new Vector3(0f, 0.8f, 0f)),
                cameraObject.transform.rotation, 18f, false, true);
    }

    private static void CreateLabel(Transform parent, string value, Vector3 position, Quaternion rotation)
    {
        var label = new GameObject(value.Replace(' ', '_'));
        label.transform.SetParent(parent, false);
        label.transform.localPosition = position;
        label.transform.localRotation = rotation;
        var text = label.AddComponent<TextMesh>();
        text.text = value;
        text.anchor = TextAnchor.MiddleLeft;
        text.alignment = TextAlignment.Left;
        text.characterSize = 0.08f;
        text.fontSize = 64;
        text.color = new Color(0.82f, 0.93f, 1f);
    }

    private static GameObject CreateCube(
        Transform parent, string name, Vector3 localPosition, Vector3 localScale, Material material)
    {
        var cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
        cube.name = name;
        cube.transform.SetParent(parent, false);
        cube.transform.localPosition = localPosition;
        cube.transform.localScale = localScale;
        cube.GetComponent<Renderer>().sharedMaterial = material;
        var collider = cube.GetComponent<Collider>();
        if (collider != null)
            UnityEngine.Object.DestroyImmediate(collider);
        return cube;
    }

    private static Material GetOrCreateMaterial(
        string name, Color color, float metallic, float smoothness, bool emissive = false)
    {
        Directory.CreateDirectory(MaterialFolder);
        AssetDatabase.Refresh();
        var path = $"{MaterialFolder}/{name}.mat";
        var material = AssetDatabase.LoadAssetAtPath<Material>(path);
        var shader = Shader.Find("HDRP/Lit");
        if (shader == null)
            throw new InvalidOperationException("HDRP/Lit shader was not found.");

        if (material == null)
        {
            material = new Material(shader) { name = name };
            AssetDatabase.CreateAsset(material, path);
        }
        else
        {
            material.shader = shader;
        }

        material.SetColor("_BaseColor", color);
        material.SetFloat("_Metallic", metallic);
        material.SetFloat("_Smoothness", smoothness);
        if (material.HasProperty("_EmissiveColor"))
            material.SetColor("_EmissiveColor", emissive ? color * 4f : Color.black);
        if (material.HasProperty("_EmissiveIntensity"))
            material.SetFloat("_EmissiveIntensity", emissive ? 2500f : 0f);
        if (emissive)
            material.EnableKeyword("_EMISSION");
        else
            material.DisableKeyword("_EMISSION");
        material.globalIlluminationFlags = emissive
            ? MaterialGlobalIlluminationFlags.RealtimeEmissive
            : MaterialGlobalIlluminationFlags.EmissiveIsBlack;
        EditorUtility.SetDirty(material);
        AssetDatabase.SaveAssets();
        return material;
    }
}
#endif
