#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad] public static class OxidationInteriorTrimCheck
{
    static OxidationInteriorTrimCheck(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(!File.Exists("OxidationInteriorTrim.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("OxidationInteriorTrim.once");
        try
        {
            var cycle=UnityEngine.Object.FindAnyObjectByType<IntegratedOxidationCycle>();Check(cycle,"Oxidation tool missing");
            var scene=cycle.gameObject.scene;Check(EditorSceneManager.SaveScene(scene),"Initial save failed");
            string backup="Tools/Backups/BeforeOxidationInteriorTrim-20261023/FactoryBeforeTrim.unity";if(!File.Exists(backup))File.Copy(scene.path,backup);
            var all=cycle.GetComponentsInChildren<Renderer>(true);var text=all.Single(r=>r.name=="REF_SystemMark");var back=all.Single(r=>r.name=="Demo_Enclosure_Back");
            cycle.ConfigureInteriorPanels();back.enabled=true;
            var states=all.ToDictionary(r=>r,r=>r.enabled);var poses=cycle.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t,t=>t.localToWorldMatrix);
            try
            {
                cycle.ShowInside();Check(!text.enabled&&back.enabled,"Interior label/back wall visibility wrong");
                Check(all.Where(r=>!cycle.cutawayPanels.Contains(r)).All(r=>r.enabled==states[r]),"Unrelated internal renderer changed");
                cycle.ShowInside();Check(text.enabled&&back.enabled,"Exterior did not restore");
                Check(poses.All(p=>p.Key.localToWorldMatrix==p.Value),"Equipment transform changed");
            }
            finally{foreach(var p in states)p.Key.enabled=p.Value;}
            EditorUtility.SetDirty(cycle);EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Updated scene save failed");
            File.WriteAllText("OxidationInteriorTrim.result","OXIDATION_INTERIOR_TRIM_OK\n"+DateTime.UtcNow.ToString("O")+"\nWAFER HANDLING SYSTEM label hidden only inside; rear enclosure remains visible. Actual ShowInside hide/restore passed; unrelated renderer states and all transforms unchanged; scene saved; no server requests.");
        }
        catch(Exception e){File.WriteAllText("OxidationInteriorTrim.result","FAILED\n"+e);Debug.LogException(e);}
    }
}
#endif
