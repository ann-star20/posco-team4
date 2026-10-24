#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

public static class MOSFETFactorySceneBuilder
{
    private const string FactoryScene =
        "Assets/UnityFactorySceneHDRP/Scene_Factory/FactorySceneSample.unity";
    private const string OutputScene =
        "Assets/MOSFETInspection/Scenes/MOSFETMultiLineFactory.unity";
    private const string InspectionLineModel =
        "Assets/MOSFETInspection/Models/mosfet_inspection_line_v10.fbx";
    private const string SourceVolumeProfile =
        "Assets/UnityFactorySceneHDRP/Scene_Factory/Background/HDRPResources/VolumeProfile.asset";
    private const string OutputVolumeProfile =
        "Assets/MOSFETInspection/Settings/MOSFETFactoryVolumeProfile.asset";
    private const string GeneratedMaterialsFolder =
        "Assets/MOSFETInspection/Materials/Generated";
    private const string GeneratedRootName = "AOD4184_PRODUCTION_AREA";
    private const string BuildRequestFile = "BuildMOSFETFactory.once";

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
                BuildThreeLineFactory();
            }
            catch (Exception exception)
            {
                Debug.LogException(exception);
            }
        };
    }

    [MenuItem("MOSFET Factory/Build Three-Line Factory %#F12")]
    public static void BuildThreeLineFactory()
    {
        var scene = EditorSceneManager.OpenScene(FactoryScene, OpenSceneMode.Single);
        Directory.CreateDirectory(Path.GetDirectoryName(OutputScene) ??
                                  "Assets/MOSFETInspection/Scenes");
        if (!EditorSceneManager.SaveScene(scene, OutputScene, true))
            throw new InvalidOperationException("Could not create the MOSFET factory scene copy.");

        scene = SceneManager.GetActiveScene();
        var oldRoot = GameObject.Find(GeneratedRootName);
        if (oldRoot != null)
            UnityEngine.Object.DestroyImmediate(oldRoot);

        var factoryLines = FindFactoryLineRoots(scene);
        if (factoryLines.Count < 3)
            throw new InvalidOperationException(
                $"At least three Unity Factory line anchors are required; found {factoryLines.Count}.");

        var anchors = BuildParallelAnchors(factoryLines[0], 3);

        // Keep the factory shell and props, but remove the sample equipment and
        // crowd so the AOD4184 lines are the clear focus.
        foreach (var factoryLine in factoryLines)
            factoryLine.gameObject.SetActive(false);
        var hiddenWorkers = HideObjectsNamed(scene, "Worker");

        var model = AssetDatabase.LoadAssetAtPath<GameObject>(InspectionLineModel);
        if (model == null)
            throw new InvalidOperationException("The AOD4184 v10 FBX was not imported.");

        var generatedRoot = new GameObject(GeneratedRootName);
        Undo.RegisterCreatedObjectUndo(generatedRoot, "Build AOD4184 production area");

        var report = new StringBuilder("MOSFET_FACTORY_BUILD_OK\n");
        report.AppendLine($"hidden worker roots={hiddenWorkers}");
        var productionBounds = new Bounds();
        var tonedMaterials = new Dictionary<Material, Material>();
        var safetyGreenMaterial = GetOrCreateSafetyGreenMaterial();
        for (var i = 0; i < anchors.Length; i++)
        {
            var instance = PrefabUtility.InstantiatePrefab(model, scene) as GameObject;
            if (instance == null)
                throw new InvalidOperationException("Could not instantiate the AOD4184 line FBX.");

            instance.name = $"AOD4184_LINE_{i + 1:00}";
            var fbxAxisCorrection = instance.transform.rotation;
            instance.transform.SetParent(generatedRoot.transform, true);
            instance.transform.SetPositionAndRotation(
                anchors[i].Position, anchors[i].Rotation * fbxAxisCorrection);
            NeutralizeEmissiveMaterials(instance, tonedMaterials);

            if (!TryGetBounds(instance, out var originalBounds))
                throw new InvalidOperationException($"{instance.name} has no renderer bounds.");

            NormalizeLineScale(instance, originalBounds);
            AlignToAnchorFloor(instance, anchors[i].Position.y);

            if (!TryGetBounds(instance, out var finalBounds))
                throw new InvalidOperationException($"{instance.name} lost its renderer bounds.");
            if (finalBounds.size.y <= finalBounds.size.z)
                throw new InvalidOperationException(
                    $"{instance.name} is lying on its side: size={finalBounds.size}.");

            AddSafetyMarkings(generatedRoot.transform, finalBounds, i + 1, safetyGreenMaterial);
            if (i == 0)
                productionBounds = finalBounds;
            else
                productionBounds.Encapsulate(finalBounds);
            report.AppendLine(
                $"{instance.name} anchor={anchors[i].SourceName} center={finalBounds.center} size={finalBounds.size}");
        }

        ConfigureExposure(scene);
        var overviewCamera = AddOverviewCamera(scene, generatedRoot.transform, productionBounds);
        FocusSceneView(productionBounds, overviewCamera.transform.rotation);
        report.AppendLine($"production bounds center={productionBounds.center} size={productionBounds.size}");
        EditorSceneManager.MarkSceneDirty(scene);
        if (!EditorSceneManager.SaveScene(scene, OutputScene))
            throw new InvalidOperationException("Could not save the completed MOSFET factory scene.");

        Selection.activeGameObject = null;
        Debug.Log(report.ToString());
    }

    public static void DiagnoseFactory()
    {
        var scene = EditorSceneManager.OpenScene(FactoryScene, OpenSceneMode.Single);
        var text = new StringBuilder("MOSFET_FACTORY_DIAGNOSTIC\n");
        foreach (var root in scene.GetRootGameObjects())
        {
            text.AppendLine($"ROOT {root.name} pos={root.transform.position} active={root.activeSelf}");
            if (TryGetBounds(root, out var bounds))
                text.AppendLine($"BOUNDS {root.name} center={bounds.center} size={bounds.size}");
        }

        var model = AssetDatabase.LoadAssetAtPath<GameObject>(InspectionLineModel);
        if (model == null)
            throw new System.InvalidOperationException("v10 FBX was not imported");
        var preview = PrefabUtility.InstantiatePrefab(model) as GameObject;
        if (preview == null || !TryGetBounds(preview, out var modelBounds))
            throw new System.InvalidOperationException("v10 FBX has no renderer bounds");
        text.AppendLine($"MODEL center={modelBounds.center} size={modelBounds.size}");
        UnityEngine.Object.DestroyImmediate(preview);
        Debug.Log(text.ToString());
    }

    private static List<Transform> FindFactoryLineRoots(Scene scene)
    {
        return scene.GetRootGameObjects()
            .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
            .Where(t => t.gameObject.scene == scene)
            .Where(t => System.Text.RegularExpressions.Regex.IsMatch(t.name, @"^Line_\d{2}$"))
            .Where(t => t.parent == null ||
                        !System.Text.RegularExpressions.Regex.IsMatch(t.parent.name, @"^Line_\d{2}$"))
            .OrderBy(t => t.name, StringComparer.Ordinal)
            .ToList();
    }

    private static Anchor[] BuildParallelAnchors(Transform primary, int count)
    {
        const float spacing = 4.2f;
        var anchors = new Anchor[count];
        var startOffset = -0.5f * spacing * (count - 1);
        for (var i = 0; i < count; i++)
        {
            var position = primary.position + primary.forward * (startOffset + spacing * i);
            var frontFacingRotation = primary.rotation * Quaternion.Euler(0f, 180f, 0f);
            anchors[i] = new Anchor(position, frontFacingRotation,
                $"{primary.name}+parallel-{i + 1:00}");
        }
        return anchors;
    }

    private static void NeutralizeEmissiveMaterials(
        GameObject instance, IDictionary<Material, Material> cache)
    {
        Directory.CreateDirectory(GeneratedMaterialsFolder);
        AssetDatabase.Refresh();
        var hdrpLit = Shader.Find("HDRP/Lit");
        if (hdrpLit == null)
            throw new InvalidOperationException("The HDRP/Lit shader is not available.");
        foreach (var renderer in instance.GetComponentsInChildren<Renderer>(true))
        {
            var materials = renderer.sharedMaterials;
            for (var i = 0; i < materials.Length; i++)
            {
                var source = materials[i];
                if (source == null)
                    continue;
                if (!cache.TryGetValue(source, out var toned))
                {
                    var baseColor = source.HasProperty("_BaseColor")
                        ? source.GetColor("_BaseColor")
                        : source.HasProperty("_Color") ? source.GetColor("_Color") : source.color;
                    baseColor = new Color(
                        Mathf.GammaToLinearSpace(baseColor.r),
                        Mathf.GammaToLinearSpace(baseColor.g),
                        Mathf.GammaToLinearSpace(baseColor.b),
                        baseColor.a);
                    var brightest = Mathf.Max(baseColor.r, Mathf.Max(baseColor.g, baseColor.b));
                    var darkest = Mathf.Min(baseColor.r, Mathf.Min(baseColor.g, baseColor.b));
                    var isTextMaterial = source.name.IndexOf("label", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                         source.name.IndexOf("letter", StringComparison.OrdinalIgnoreCase) >= 0;
                    if (!isTextMaterial && brightest > 0.55f && brightest - darkest < 0.12f)
                        baseColor = new Color(0.18f, 0.18f, 0.18f, baseColor.a);
                    var metallic = source.HasProperty("_Metallic")
                        ? source.GetFloat("_Metallic") : 0f;
                    var smoothness = source.HasProperty("_Smoothness")
                        ? source.GetFloat("_Smoothness")
                        : source.HasProperty("_Glossiness") ? source.GetFloat("_Glossiness") : 0.5f;
                    var safeName = string.Concat(source.name.Select(character =>
                        Path.GetInvalidFileNameChars().Contains(character) ? '_' : character));
                    var path = $"{GeneratedMaterialsFolder}/{cache.Count:000}_{safeName}.mat";
                    toned = AssetDatabase.LoadAssetAtPath<Material>(path);
                    if (toned == null)
                    {
                        toned = new Material(hdrpLit);
                        AssetDatabase.CreateAsset(toned, path);
                    }
                    else
                    {
                        toned.shader = hdrpLit;
                    }

                    toned.SetColor("_BaseColor", baseColor);
                    toned.SetFloat("_Metallic", metallic);
                    toned.SetFloat("_Smoothness", Mathf.Clamp01(smoothness));
                    if (toned.HasProperty("_EmissiveColor"))
                        toned.SetColor("_EmissiveColor", Color.black);
                    if (toned.HasProperty("_EmissionColor"))
                        toned.SetColor("_EmissionColor", Color.black);
                    if (toned.HasProperty("_EmissiveIntensity"))
                        toned.SetFloat("_EmissiveIntensity", 0f);
                    toned.DisableKeyword("_EMISSION");
                    toned.globalIlluminationFlags = MaterialGlobalIlluminationFlags.EmissiveIsBlack;
                    if (baseColor.a < 0.99f)
                    {
                        toned.SetFloat("_SurfaceType", 1f);
                        toned.SetFloat("_BlendMode", 0f);
                        toned.SetFloat("_ZWrite", 0f);
                        toned.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                        toned.renderQueue = 3000;
                    }
                    else
                    {
                        toned.SetFloat("_SurfaceType", 0f);
                        toned.SetFloat("_ZWrite", 1f);
                        toned.DisableKeyword("_SURFACE_TYPE_TRANSPARENT");
                        toned.renderQueue = -1;
                    }
                    EditorUtility.SetDirty(toned);
                    cache.Add(source, toned);
                }
                materials[i] = toned;
            }
            renderer.sharedMaterials = materials;
        }
        AssetDatabase.SaveAssets();
    }

    private static void ConfigureExposure(Scene scene)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(OutputVolumeProfile) ??
                                  "Assets/MOSFETInspection/Settings");
        AssetDatabase.Refresh();
        var profile = AssetDatabase.LoadAssetAtPath<VolumeProfile>(OutputVolumeProfile);
        if (profile == null)
        {
            if (!AssetDatabase.CopyAsset(SourceVolumeProfile, OutputVolumeProfile))
                throw new InvalidOperationException("Could not create the MOSFET factory volume profile.");
            AssetDatabase.ImportAsset(OutputVolumeProfile);
            profile = AssetDatabase.LoadAssetAtPath<VolumeProfile>(OutputVolumeProfile);
        }
        if (profile == null)
            throw new InvalidOperationException("The MOSFET factory volume profile could not be loaded.");

        var exposure = profile.components.FirstOrDefault(component => component.name == "Exposure");
        if (exposure != null)
        {
            var serializedExposure = new SerializedObject(exposure);
            SetVolumeFloat(serializedExposure, "compensation", 0f);
            serializedExposure.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(exposure);
        }

        foreach (var volume in scene.GetRootGameObjects()
                     .SelectMany(root => root.GetComponentsInChildren<Volume>(true)))
        {
            if (volume.sharedProfile != null &&
                AssetDatabase.GetAssetPath(volume.sharedProfile) == SourceVolumeProfile)
                volume.sharedProfile = profile;
        }
        AssetDatabase.SaveAssets();
    }

    private static void SetVolumeFloat(SerializedObject component, string parameter, float value)
    {
        var property = component.FindProperty(parameter);
        if (property == null)
            return;
        var overrideState = property.FindPropertyRelative("m_OverrideState");
        var parameterValue = property.FindPropertyRelative("m_Value");
        if (overrideState != null)
            overrideState.boolValue = true;
        if (parameterValue != null)
            parameterValue.floatValue = value;
    }

    private static int HideObjectsNamed(Scene scene, string objectName)
    {
        var matches = scene.GetRootGameObjects()
            .SelectMany(root => root.GetComponentsInChildren<Transform>(true))
            .Where(transform => string.Equals(
                transform.name, objectName, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        foreach (var match in matches)
            match.gameObject.SetActive(false);
        return matches.Length;
    }

    private static void NormalizeLineScale(GameObject instance, Bounds bounds)
    {
        var horizontalSize = Mathf.Max(bounds.size.x, bounds.size.z);
        if (horizontalSize <= 0.001f)
            throw new InvalidOperationException("The imported inspection line has an invalid scale.");

        // Keep believable real-world dimensions while correcting FBX unit mismatches.
        const float targetLength = 14f;
        if (horizontalSize < 7f || horizontalSize > 28f)
        {
            var factor = targetLength / horizontalSize;
            instance.transform.localScale *= factor;
        }
    }

    private static void AlignToAnchorFloor(GameObject instance, float floorY)
    {
        if (!TryGetBounds(instance, out var bounds))
            return;
        var delta = new Vector3(0f, floorY - bounds.min.y, 0f);
        instance.transform.position += delta;
    }

    private static void AddLineNumberSign(Transform parent, Bounds bounds, int lineNumber)
    {
        var sign = new GameObject($"LINE_{lineNumber:00}_SIGN");
        sign.transform.SetParent(parent, true);
        sign.transform.position = new Vector3(bounds.center.x, bounds.max.y + 0.55f, bounds.center.z);
        sign.transform.rotation = Quaternion.Euler(0f, 180f, 0f);

        var text = sign.AddComponent<TextMesh>();
        text.text = $"AOD4184 INSPECTION LINE {lineNumber:00}";
        text.anchor = TextAnchor.MiddleCenter;
        text.alignment = TextAlignment.Center;
        text.characterSize = 0.055f;
        text.fontSize = 64;
        text.color = new Color(0.82f, 0.93f, 1f, 1f);
    }

    private static Material GetOrCreateSafetyGreenMaterial()
    {
        Directory.CreateDirectory(GeneratedMaterialsFolder);
        AssetDatabase.Refresh();

        const string materialPath = GeneratedMaterialsFolder + "/SafetyZoneGreen.mat";
        var material = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
        var shader = Shader.Find("HDRP/Lit");
        if (shader == null)
            throw new InvalidOperationException("HDRP/Lit shader was not found.");

        if (material == null)
        {
            material = new Material(shader) { name = "Safety Zone Green" };
            AssetDatabase.CreateAsset(material, materialPath);
        }
        else
        {
            material.shader = shader;
        }

        var safetyGreen = new Color(0.015f, 0.24f, 0.105f, 1f);
        if (material.HasProperty("_BaseColor"))
            material.SetColor("_BaseColor", safetyGreen);
        if (material.HasProperty("_Metallic"))
            material.SetFloat("_Metallic", 0f);
        if (material.HasProperty("_Smoothness"))
            material.SetFloat("_Smoothness", 0.2f);
        if (material.HasProperty("_EmissiveColor"))
            material.SetColor("_EmissiveColor", Color.black);
        material.DisableKeyword("_EMISSION");
        material.globalIlluminationFlags = MaterialGlobalIlluminationFlags.EmissiveIsBlack;
        EditorUtility.SetDirty(material);
        AssetDatabase.SaveAssets();
        return material;
    }

    private static void AddSafetyMarkings(
        Transform parent, Bounds bounds, int lineNumber, Material safetyGreenMaterial)
    {
        var markingRoot = new GameObject($"LINE_{lineNumber:00}_SAFETY_MARKINGS");
        markingRoot.transform.SetParent(parent, true);

        const float clearance = 0.65f;
        const float stripeWidth = 0.08f;
        const float stripeHeight = 0.02f;
        var outerWidth = bounds.size.x + clearance * 2f;
        var outerDepth = bounds.size.z + clearance * 2f;
        var floorY = bounds.min.y + stripeHeight * 0.5f + 0.005f;

        AddSafetyStripe(markingRoot.transform, "Front Safety Stripe",
            new Vector3(bounds.center.x, floorY, bounds.center.z - outerDepth * 0.5f),
            new Vector3(outerWidth, stripeHeight, stripeWidth), safetyGreenMaterial);
        AddSafetyStripe(markingRoot.transform, "Back Safety Stripe",
            new Vector3(bounds.center.x, floorY, bounds.center.z + outerDepth * 0.5f),
            new Vector3(outerWidth, stripeHeight, stripeWidth), safetyGreenMaterial);
        AddSafetyStripe(markingRoot.transform, "Left Safety Stripe",
            new Vector3(bounds.center.x - outerWidth * 0.5f, floorY, bounds.center.z),
            new Vector3(stripeWidth, stripeHeight, outerDepth), safetyGreenMaterial);
        AddSafetyStripe(markingRoot.transform, "Right Safety Stripe",
            new Vector3(bounds.center.x + outerWidth * 0.5f, floorY, bounds.center.z),
            new Vector3(stripeWidth, stripeHeight, outerDepth), safetyGreenMaterial);
    }

    private static void AddSafetyStripe(
        Transform parent, string name, Vector3 position, Vector3 scale, Material material)
    {
        var stripe = GameObject.CreatePrimitive(PrimitiveType.Cube);
        stripe.name = name;
        stripe.transform.SetParent(parent, true);
        stripe.transform.position = position;
        stripe.transform.localScale = scale;
        stripe.GetComponent<Renderer>().sharedMaterial = material;

        var collider = stripe.GetComponent<Collider>();
        if (collider != null)
            UnityEngine.Object.DestroyImmediate(collider);
    }

    private static Camera AddOverviewCamera(Scene scene, Transform parent, Bounds bounds)
    {
        var cameraObject = new GameObject("AOD4184_FACTORY_OVERVIEW_CAMERA");
        cameraObject.transform.SetParent(parent, true);
        var span = Mathf.Max(bounds.size.x, bounds.size.z);
        var focus = bounds.center + Vector3.up * 0.6f;
        cameraObject.transform.position = focus + new Vector3(span * 0.7f, span * 0.55f, span * 0.9f);
        cameraObject.transform.LookAt(focus);
        var camera = cameraObject.AddComponent<Camera>();
        foreach (var otherCamera in scene.GetRootGameObjects()
                     .SelectMany(root => root.GetComponentsInChildren<Camera>(true)))
            otherCamera.enabled = false;
        camera.enabled = true;
        camera.fieldOfView = 44f;
        return camera;
    }

    private static void FocusSceneView(Bounds bounds, Quaternion cameraRotation)
    {
        var sceneView = SceneView.lastActiveSceneView;
        if (sceneView == null)
            return;

        var span = Mathf.Max(bounds.size.x, bounds.size.z);
        var focus = bounds.center + Vector3.up * 0.6f;
        sceneView.LookAt(focus, cameraRotation, Mathf.Max(6f, span * 0.52f), false, true);
        sceneView.Repaint();
    }

    private readonly struct Anchor
    {
        public Anchor(Vector3 position, Quaternion rotation, string sourceName)
        {
            Position = position;
            Rotation = rotation;
            SourceName = sourceName;
        }

        public Vector3 Position { get; }
        public Quaternion Rotation { get; }
        public string SourceName { get; }
    }

    private static bool TryGetBounds(GameObject root, out Bounds bounds)
    {
        var renderers = root.GetComponentsInChildren<Renderer>(true);
        if (renderers.Length == 0)
        {
            bounds = default;
            return false;
        }
        bounds = renderers[0].bounds;
        for (var i = 1; i < renderers.Length; i++)
            bounds.Encapsulate(renderers[i].bounds);
        return true;
    }
}
#endif
