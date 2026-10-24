#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad] public static class HideEquipmentIcons
{
    static HideEquipmentIcons(){EditorApplication.update+=Check;}
    static void Check()
    {
        if(!File.Exists("HideEquipmentIcons.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        File.Delete("HideEquipmentIcons.once");
        try
        {
            int count=0;
            foreach(SceneView view in SceneView.sceneViews){view.drawGizmos=false;count++;}
            SceneView.RepaintAll();
            if(count==0)throw new InvalidOperationException("No Scene view is open");
            foreach(SceneView view in SceneView.sceneViews)if(view.drawGizmos)throw new InvalidOperationException("Scene gizmos are still enabled");
            File.WriteAllText("HideEquipmentIcons.result","SCENE_GIZMOS_HIDDEN\n"+DateTime.UtcNow.ToString("O")+"\nScene views: "+count+"\nEditor helper visibility only. Camera and light components unchanged.");
        }
        catch(Exception e){File.WriteAllText("HideEquipmentIcons.result","FAILED\n"+e);Debug.LogException(e);}
    }
}
#endif
