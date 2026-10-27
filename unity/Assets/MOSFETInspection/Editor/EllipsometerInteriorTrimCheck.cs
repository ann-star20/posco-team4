#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad] public static class EllipsometerInteriorTrimCheck
{
    static EllipsometerInteriorTrimCheck(){EditorApplication.update+=Run;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Run()
    {
        if(!File.Exists("EllipsometerInteriorTrim.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("EllipsometerInteriorTrim.once");
        try
        {
            var cycle=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();Check(cycle,"Ellipsometer missing");
            var scene=cycle.gameObject.scene;Check(EditorSceneManager.SaveScene(scene),"Scene save failed");
            string backup="Tools/Backups/BeforeEllipsometerInteriorTrim-20261023/FactoryBeforeTrim.unity";
            if(!File.Exists(backup))File.Copy(scene.path,backup);
            var all=cycle.GetComponentsInChildren<Renderer>(true);
            var trim=all.Where(EllipsometerCycle.InteriorTrim).ToArray();
            var right=all.Where(r=>r.name.StartsWith("Right_Service")).ToArray();
            Check(trim.Count(r=>r.name.StartsWith("Indigo_Header"))==4,"Expected four purple border parts");
            Check(trim.Count(r=>r.name.StartsWith("Equipment_Name")||r.name.StartsWith("Equipment_Subtitle"))==2,"Expected title and subtitle");
            Check(right.Length==2,"Expected two right service panels");
            cycle.ConfigureInteriorPanels();foreach(var r in right)r.enabled=true;
            var states=all.ToDictionary(r=>r,r=>r.enabled);
            var matrices=cycle.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t,t=>t.localToWorldMatrix);
            try
            {
                cycle.ShowInside();Check(trim.All(r=>!r.enabled),"Floating border or text remains visible");
                Check(right.All(r=>r.enabled),"Right wall hidden in interior view");
                Check(all.Where(r=>!cycle.cutawayPanels.Contains(r)).All(r=>r.enabled==states[r]),"Unrelated renderer changed");
                cycle.ShowInside();Check(trim.All(r=>r.enabled)&&right.All(r=>r.enabled),"Exterior visibility not restored");
                Check(matrices.All(p=>p.Key.localToWorldMatrix==p.Value),"Equipment transform changed");
            }
            finally{foreach(var p in states)p.Key.enabled=p.Value;}
            EditorUtility.SetDirty(cycle);EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Updated scene save failed");
            File.WriteAllText("EllipsometerInteriorTrim.result","ELLIPSOMETER_INTERIOR_TRIM_OK\n"+DateTime.UtcNow.ToString("O")+"\nPurple border=4, labels=2 hidden only inside; right panels=2 remain visible.\nActual ShowInside hide/restore passed; other renderers and all transforms unchanged; scene saved; no server requests.");
        }
        catch(Exception e){File.WriteAllText("EllipsometerInteriorTrim.result","FAILED\n"+e);Debug.LogException(e);}
    }
}
#endif
