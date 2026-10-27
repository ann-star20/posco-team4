#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class OpenMOSFETFactorySceneOnce
{
    private const string RequestFile = "OpenMOSFETFactory.once";
    private const string ScenePath =
        "Assets/MOSFETInspection/Scenes/MOSFETMultiLineFactory.unity";
    private const string ProductionRootName = "AOD4184_PRODUCTION_AREA";

    [InitializeOnLoadMethod]
    private static void OpenRequestedScene()
    {
        var requestPath = Path.Combine(Directory.GetCurrentDirectory(), RequestFile);
        if (!File.Exists(requestPath))
            return;

        File.Delete(requestPath);
        EditorApplication.delayCall += OpenAndFocus;
    }

    [MenuItem("MOSFET Factory/Open Updated Three-Line Scene")]
    public static void OpenAndFocus()
    {
        EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        var productionRoot = GameObject.Find(ProductionRootName);
        if (productionRoot == null)
        {
            Debug.LogError($"{ProductionRootName} was not found in {ScenePath}.");
            return;
        }

        Selection.activeGameObject = productionRoot;
        if (SceneView.lastActiveSceneView != null)
        {
            SceneView.lastActiveSceneView.FrameSelected();
            SceneView.lastActiveSceneView.Repaint();
        }

        Debug.Log($"MOSFET_FACTORY_SCENE_OPENED\n{ScenePath}");
    }
}
#endif
