#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

public static class SmallFabPreviewCapture
{
    static double readyAt;
    [InitializeOnLoadMethod]
    static void Requested()
    {
        if (!File.Exists("CaptureSmallFab.once")) return;
        readyAt = EditorApplication.timeSinceStartup + 3;
        EditorApplication.update += CaptureWhenReady;
    }
    static void CaptureWhenReady()
    {
        if (EditorApplication.timeSinceStartup < readyAt || EditorApplication.isCompiling) return;
        EditorApplication.update -= CaptureWhenReady;
        File.Delete("CaptureSmallFab.once");
        try
        {
            var obj = GameObject.Find("FAB_OVERVIEW_CAMERA");
            if (!obj) throw new InvalidOperationException("Open the corrected fab scene first.");
            var camera = obj.GetComponent<Camera>();
            var rt = new RenderTexture(1400,1000,24,RenderTextureFormat.ARGB32);
            rt.Create();
            var request = new RenderPipeline.StandardRequest { destination = rt };
            for (int i=0;i<8;i++) RenderPipeline.SubmitRenderRequest(camera,request);
            var old = RenderTexture.active; RenderTexture.active = rt;
            var image = new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);
            image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0); image.Apply();
            var path = Path.Combine(Directory.GetCurrentDirectory(),"SmallFab_Unity_Preview.png");
            File.WriteAllBytes(path,image.EncodeToPNG());
            RenderTexture.active = old; rt.Release();
            UnityEngine.Object.DestroyImmediate(rt); UnityEngine.Object.DestroyImmediate(image);
            File.WriteAllText("SmallFabCapture.result","CAPTURE_OK " + path);
        }
        catch (Exception e) { File.WriteAllText("SmallFabCapture.result",e.ToString());Debug.LogException(e); }
    }
}
#endif
