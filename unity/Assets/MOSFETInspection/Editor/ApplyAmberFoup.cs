#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEditor.Rendering.HighDefinition;
using UnityEngine;

[InitializeOnLoad] public static class ApplyAmberFoup
{
    const string Base="Assets/MOSFETInspection/",Backup="Tools/Backups/BeforeAmberFoup-20261023/";
    static ApplyAmberFoup(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static string PathFrom(Transform t,Transform root)=>t==root?"":PathFrom(t.parent,root)+(t.parent==root?"":"/")+t.name;
    static void Drive(IEnumerator iterator)
    {
        var stack=new Stack<IEnumerator>();stack.Push(iterator);int count=0;
        while(stack.Count>0){Check(++count<60000,"Equipment replay timed out");var top=stack.Peek();if(!top.MoveNext()){stack.Pop();continue;}if(top.Current is IEnumerator child)stack.Push(child);}
    }
    static void Tick()
    {
        if(!File.Exists("ApplyAmberFoup.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("ApplyAmberFoup.once");
        try{Apply();}catch(Exception e){File.WriteAllText("ApplyAmberFoup.result","FAILED\n"+e);Debug.LogException(e);}
    }
    static void Apply()
    {
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();Check(EditorSceneManager.SaveScene(scene),"Initial save failed");
        File.Copy(scene.path,Backup+"FactoryBeforeUnityApply.unity",true);
        AssetDatabase.ImportAsset(Base+"Models/OHT/FOUP_300mm_Concept.fbx",ImportAssetOptions.ForceSynchronousImport);
        var asset=AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/OHT/FOUP_300mm_Concept.fbx");Check(asset,"FOUP FBX missing");
        var source=asset.GetComponentsInChildren<MeshFilter>(true).ToDictionary(f=>PathFrom(f.transform,asset.transform));
        var roots=scene.GetRootGameObjects().SelectMany(g=>g.GetComponentsInChildren<Transform>(true)).Where(t=>t.name=="LoadPort_Dock_Anchor").Select(t=>t.parent).Distinct().ToArray();
        Check(roots.Length>=7,"Expected existing tool, OHT and stocker FOUPs");
        var poses=scene.GetRootGameObjects().SelectMany(g=>g.GetComponentsInChildren<Transform>(true)).ToDictionary(t=>t,t=>(t.parent,t.localPosition,t.localRotation,t.localScale));
        var mats=AssetDatabase.FindAssets("t:Material",new[]{Base+"Materials/OHT"}).Select(g=>AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g))).ToDictionary(m=>m.name);
        foreach(var m in AssetDatabase.FindAssets("t:Material",new[]{Base+"Materials"}).Select(g=>AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g))))
        {
            if(m.name!="FOUP_Amber_Polymer"&&m.name!="FOUP_Door_Polymer")continue;
            bool amber=m.name=="FOUP_Amber_Polymer";
            m.SetColor("_BaseColor",amber?new Color(1,.23f,.025f,.48f):new Color(.065f,.085f,.095f,1));
            m.SetFloat("_SurfaceType",amber?1:0);m.SetFloat("_BlendMode",0);m.SetFloat("_Smoothness",amber?.78f:.63f);
            if(amber){m.SetFloat("_DoubleSidedEnable",1);m.SetFloat("_TransparentBackfaceEnable",1);}
            m.renderQueue=amber?3000:2000;
            HDShaderUtils.ResetMaterialKeywords(m);Check(!amber||m.IsKeywordEnabled("_SURFACE_TYPE_TRANSPARENT"),"Transparent material setup failed");EditorUtility.SetDirty(m);
        }
        int meshes=0;
        foreach(var root in roots)foreach(var pair in source)
        {
            var target=root.Find(pair.Key);Check(target,"Existing FOUP node missing: "+root.name+"/"+pair.Key);
            var filter=target.GetComponent<MeshFilter>();Check(filter,"Existing mesh filter missing");
            filter.sharedMesh=pair.Value.sharedMesh;
            var renderer=target.GetComponent<Renderer>();renderer.sharedMaterials=pair.Value.GetComponent<Renderer>().sharedMaterials.Select(m=>mats[m.name]).ToArray();meshes++;
        }
        foreach(var p in poses){var t=p.Key;var v=p.Value;Check(t&&t.parent==v.Item1&&t.localPosition==v.Item2&&t.localRotation==v.Item3&&t.localScale==v.Item4,"Existing transform changed: "+t.name);}
        EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"FOUP scene save failed");AssetDatabase.SaveAssets();
        var ox=UnityEngine.Object.FindAnyObjectByType<IntegratedOxidationCycle>();var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();
        try
        {
            ox.Initialize();ox.validationDelta=1f/30;ox.transportControlled=false;var parent=ox.wafer.parent;Drive(ox.Cycle());Check(ox.completed&&!ox.failed&&ox.wafer.parent==parent,"Oxidation door/wafer return failed");ox.ResetPreview();
            film.Initialize();film.validationDelta=1f/30;film.transportControlled=false;film.SetCsvTest(null);film.lotHeld=false;parent=film.wafer.parent;Drive(film.Cycle());Check(film.completed&&!film.failed&&film.wafer.parent==parent,"Ellipsometer door/wafer return failed");film.ResetPreview();
            ion.Initialize();ion.validationDelta=1f/30;ion.transportControlled=false;ion.SetCsvTest(null);ion.lotQualityGate=null;parent=ion.wafer.parent;Drive(ion.Cycle());Check(ion.completed&&!ion.failed&&ion.wafer.parent==parent,"Ion door/wafer return failed");ion.ResetPreview();
            File.WriteAllText("ApplyAmberFoup.result","EXISTING_FOUP_AMBER_UNITY_OK\n"+DateTime.UtcNow.ToString("O")+"\nExisting FOUP instances="+roots.Length+", mesh mappings="+meshes+"; all original transforms/anchors preserved; HDRP amber transparency enabled.\nActual oxidation, ellipsometer and ion door/wafer cycles passed offline. Scene saved before replay; no server requests.");
        }
        finally{EditorSceneManager.OpenScene(scene.path);}
    }
}
#endif
