#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;
using UnityEngine.SceneManagement;

[InitializeOnLoad] public static class FactoryWhiteBackground
{
    const string ScenePreference="UnityMOSFETFactory.WhiteSceneBackground";
    static bool whiteScene=EditorPrefs.GetBool(ScenePreference,false);
    static int captureFrames;
    static FactoryWhiteBackground(){EditorApplication.update+=Check;SceneView.duringSceneGui+=MaintainScene;}
    static void MaintainScene(SceneView view)
    {
        if(!whiteScene||!view.camera)return;
        view.sceneViewState.showSkybox=false;
        var camera=view.camera;camera.clearFlags=CameraClearFlags.SolidColor;camera.backgroundColor=Color.white;
        var hd=camera.GetComponent<HDAdditionalCameraData>();
        if(hd){hd.clearColorMode=HDAdditionalCameraData.ClearColorMode.Color;hd.backgroundColorHDR=Color.white;}
    }
    static void ApplySceneBackground()
    {
        whiteScene=true;EditorPrefs.SetBool(ScenePreference,true);int count=0;
        foreach(SceneView view in SceneView.sceneViews){MaintainScene(view);view.Repaint();count++;}
        if(count==0)throw new InvalidOperationException("No Scene views found");
        EditorApplication.delayCall+=VerifySceneBackground;
    }
    static void VerifySceneBackground()
    {
        try
        {
            int count=0;var report=new List<string>{"SCENE_HDRP_WHITE_BACKGROUND_OK",DateTime.UtcNow.ToString("O")};
            foreach(SceneView view in SceneView.sceneViews)
            {
                MaintainScene(view);var c=view.camera;var hd=c.GetComponent<HDAdditionalCameraData>();
                if(view.sceneViewState.showSkybox||c.clearFlags!=CameraClearFlags.SolidColor||c.backgroundColor!=Color.white||hd&&(hd.clearColorMode!=HDAdditionalCameraData.ClearColorMode.Color||hd.backgroundColorHDR!=Color.white))throw new InvalidOperationException("Scene camera background not white");
                report.Add("Scene camera: "+c.name+" / white / "+(hd?"HDRP":"standard"));count++;
            }
            if(count==0)throw new InvalidOperationException("No Scene cameras found");
            File.WriteAllText("FactorySceneWhiteFix.result",string.Join("\n",report));SceneView.RepaintAll();
            captureFrames=0;EditorApplication.update-=CaptureScene;EditorApplication.update+=CaptureScene;
        }
        catch(Exception e){File.WriteAllText("FactorySceneWhiteFix.result","FAILED\n"+e);Debug.LogException(e);}
    }
    static void CaptureScene()
    {
        if(++captureFrames<12)return;EditorApplication.update-=CaptureScene;
        var view=SceneView.lastActiveSceneView;var rt=view&&view.camera?view.camera.targetTexture:null;
        if(!rt)return;
        var previous=RenderTexture.active;Texture2D image=null;
        try
        {
            RenderTexture.active=rt;image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);
            image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();
            Directory.CreateDirectory("Tools/Previews");File.WriteAllBytes("Tools/Previews/Scene-White-Background.png",image.EncodeToPNG());
            File.AppendAllText("FactorySceneWhiteFix.result","\nScene render capture: Tools/Previews/Scene-White-Background.png");
        }
        catch(Exception e){File.AppendAllText("FactorySceneWhiteFix.result","\nCapture unavailable: "+e.Message);}
        finally{RenderTexture.active=previous;if(image)UnityEngine.Object.DestroyImmediate(image);}
    }
    static void Check()
    {
        if(File.Exists("FactorySceneWhiteFix.once")&&!EditorApplication.isCompiling&&!EditorApplication.isUpdating)
        {
            File.Delete("FactorySceneWhiteFix.once");
            try{ApplySceneBackground();}catch(Exception e){File.WriteAllText("FactorySceneWhiteFix.result","FAILED\n"+e);Debug.LogException(e);}
        }
        if(!File.Exists("FactoryWhiteBackground.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("FactoryWhiteBackground.once");
        try{Apply();}catch(Exception e){File.WriteAllText("FactoryWhiteBackground.result","FAILED\n"+e);Debug.LogException(e);}
    }
    static void Apply()
    {
        // Scene background is a cached editor preference without a public setter.
        var field=typeof(SceneView).GetField("kSceneViewBackground",BindingFlags.Static|BindingFlags.NonPublic);
        object pref=field?.GetValue(null)??throw new MissingFieldException("SceneView background preference not found");
        var color=pref.GetType().GetProperty("Color")??throw new MissingMemberException("SceneView preference Color not found");
        var cameras=new List<Camera>();
        foreach(var c in UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include))
            if(c.cameraType==CameraType.Game&&c.targetTexture==null&&c.gameObject.scene.IsValid()&&!EditorUtility.IsPersistent(c))cameras.Add(c);
        if(cameras.Count==0)throw new InvalidOperationException("No factory display cameras found");
        string backup="Tools/Backups/WhiteBackground-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);
        File.WriteAllText(Path.Combine(backup,"SceneBackground.txt"),EditorPrefs.GetString("Scene/Background","")+"\n"+color.GetValue(pref));
        var scenes=new Dictionary<string,Scene>();
        foreach(var c in cameras)scenes[c.gameObject.scene.path]=c.gameObject.scene;
        int index=0;
        foreach(var scene in scenes.Values)
        {
            if(string.IsNullOrEmpty(scene.path))throw new InvalidOperationException("Save the open factory scene before changing its background");
            File.Copy(scene.path,Path.Combine(backup,(index++)+"-"+Path.GetFileName(scene.path)),true);
        }
        color.SetValue(pref,Color.white);
        string saved=(string)pref.GetType().GetMethod("ToUniqueString").Invoke(pref,null);
        EditorPrefs.SetString("Scene/Background",saved);
        int views=0;
        ApplySceneBackground();
        foreach(SceneView view in SceneView.sceneViews)views++;
        var report=new List<string>{"FACTORY_WHITE_BACKGROUND_OK",DateTime.UtcNow.ToString("O"),"Backup: "+backup,"Scene views: "+views};
        foreach(var c in cameras)
        {
            Undo.RecordObject(c,"Factory white background");c.clearFlags=CameraClearFlags.SolidColor;c.backgroundColor=Color.white;EditorUtility.SetDirty(c);
            var hd=c.GetComponent<HDAdditionalCameraData>();
            if(hd){Undo.RecordObject(hd,"Factory white background");hd.clearColorMode=HDAdditionalCameraData.ClearColorMode.Color;hd.backgroundColorHDR=Color.white;EditorUtility.SetDirty(hd);}
            if(c.clearFlags!=CameraClearFlags.SolidColor||c.backgroundColor!=Color.white||hd&&(hd.clearColorMode!=HDAdditionalCameraData.ClearColorMode.Color||hd.backgroundColorHDR!=Color.white))throw new InvalidOperationException("Camera background did not update: "+c.name);
            report.Add("Camera: "+c.name+" / white / "+(hd?"HDRP":"standard"));
        }
        foreach(var scene in scenes.Values){EditorSceneManager.MarkSceneDirty(scene);if(!EditorSceneManager.SaveScene(scene))throw new IOException("Scene save failed: "+scene.path);}
        if((Color)color.GetValue(pref)!=Color.white)throw new InvalidOperationException("Scene background is not white");
        SceneView.RepaintAll();UnityEditorInternal.InternalEditorUtility.RepaintAllViews();
        report.Add("Camera backgrounds and Scene preference only. Lighting, materials and process logic unchanged.");
        File.WriteAllText("FactoryWhiteBackground.result",string.Join("\n",report));
    }
}
#endif
