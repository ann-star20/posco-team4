#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

public static class CleanroomCameraQuality
{
    [InitializeOnLoadMethod] static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(!File.Exists("CleanroomQuality.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("CleanroomQuality.once");
        try{Apply();}catch(Exception e){File.WriteAllText("CleanroomQuality.result",e.ToString());Debug.LogException(e);}
    }
    [MenuItem("MOSFET Factory/Improve Cleanroom Camera Quality")]
    public static void Apply()
    {
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(scene.path!="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity")throw new Exception("Open corrected cleanroom scene first.");
        if(scene.isDirty&&!EditorSceneManager.SaveScene(scene))throw new Exception("Cannot save scene.");
        var backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeCameraQuality.unity");
        if(!AssetDatabase.CopyAsset(scene.path,backup))throw new Exception("Backup failed.");
        var cameras=scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Camera>(true)).ToArray();
        var overview=cameras.First(c=>c.name=="FAB_OVERVIEW_CAMERA");
        Capture(overview,"Cleanroom_Quality_Before.png");
        foreach(var camera in cameras)
        {
            var hd=camera.GetComponent<HDAdditionalCameraData>();if(!hd)continue;
            hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;
            // Keep full resolution and avoid motion-dependent temporal smearing of thin machine parts.
            hd.allowDynamicResolution=false;camera.allowDynamicResolution=false;
            EditorUtility.SetDirty(hd);EditorUtility.SetDirty(camera);
            if(hd.antialiasing!=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing||hd.allowDynamicResolution)
                throw new Exception("Camera quality validation failed: "+camera.name);
        }
        EditorSceneManager.SaveScene(scene);
        Capture(overview,"Cleanroom_Quality_After.png");
        File.WriteAllText("CleanroomQuality.result","CAMERA_QUALITY_OK\ncameras="+cameras.Length+"\nSMAA=High; dynamic resolution=off\nbackup="+backup);
    }
    static void Capture(Camera camera,string file)
    {
        var rt=new RenderTexture(2560,1440,24);rt.Create();var old=RenderTexture.active;
        for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});
        RenderTexture.active=rt;var image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);
        image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();File.WriteAllBytes(file,image.EncodeToPNG());
        RenderTexture.active=old;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);
    }
}
#endif
