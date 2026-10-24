#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad] public static class IonInteriorTrimCheck
{
    static IonInteriorTrimCheck(){EditorApplication.update+=Run;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Run()
    {
        if(!File.Exists("IonInteriorTrim.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("IonInteriorTrim.once");
        try
        {
            var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();Check(ion,"Ion implanter missing");
            var scene=ion.gameObject.scene;
            Check(EditorSceneManager.SaveScene(scene),"Scene save failed");
            string backup="Tools/Backups/BeforeIonInteriorTrim-20261023/FactoryBeforeTrim.unity";
            if(!File.Exists(backup))File.Copy(scene.path,backup);
            var all=ion.GetComponentsInChildren<Renderer>(true);
            var trim=all.Where(IonImplantCycle.InteriorTrim).ToArray();
            Check(trim.Count(r=>r.name=="Front_Header"||r.name=="Rear_Header")==2,"Expected two decorative headers");
            Check(trim.Count(r=>r.name.StartsWith("Port_Status_Panel_"))==4,"Expected four indicator housings");
            Check(trim.Count(r=>r.name.StartsWith("Port_Status_LED"))==24,"Expected 24 indicator lights");
            int missing=trim.Count(r=>!ion.cutawayPanels.Contains(r));
            ion.cutawayPanels=ion.cutawayPanels.Concat(trim).Distinct().ToArray();
            var matrices=ion.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t,t=>t.localToWorldMatrix);
            var states=all.ToDictionary(r=>r,r=>r.enabled);
            var cameras=UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include,FindObjectsSortMode.None).ToDictionary(c=>c,c=>c.enabled);
            try
            {
                ion.ShowInside();Check(trim.All(r=>!r.enabled),"Interior trim remains visible");
                Check(all.Where(r=>!ion.cutawayPanels.Contains(r)&&r!=ion.beam).All(r=>r.enabled==states[r]),"Internal part visibility changed");
                ion.ShowInside();Check(trim.All(r=>r.enabled),"Exterior trim not restored");
                Check(matrices.All(p=>p.Key.localToWorldMatrix==p.Value),"Equipment transform changed");
            }
            finally{foreach(var p in states)p.Key.enabled=p.Value;foreach(var p in cameras)p.Key.enabled=p.Value;}
            EditorUtility.SetDirty(ion);EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Updated scene save failed");
            File.WriteAllText("IonInteriorTrim.result","ION_INTERIOR_TRIM_OK\n"+DateTime.UtcNow.ToString("O")+"\nHeaders=2, housings=4, LEDs=24; newly included="+missing+"\nActual ShowInside hide/restore passed; unrelated internal renderers and all transforms unchanged; saved scene; no server requests.");
        }
        catch(Exception e){File.WriteAllText("IonInteriorTrim.result","FAILED\n"+e);Debug.LogException(e);}
    }
}
#endif
