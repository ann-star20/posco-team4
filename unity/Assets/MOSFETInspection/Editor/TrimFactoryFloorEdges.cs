#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

// One-shot edit of the room shell. It never changes the editor layout or starts Play.
[InitializeOnLoad] public static class TrimFactoryFloorEdges
{
    static TrimFactoryFloorEdges(){EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(!File.Exists("TrimFactoryFloorEdges.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("TrimFactoryFloorEdges.once");
        try{Apply();}catch(Exception e){File.WriteAllText("TrimFactoryFloorEdges.result","FAILED\n"+e);Debug.LogException(e);}
    }
    static Bounds BoundsOf(Transform t){var rs=t.GetComponentsInChildren<Renderer>(true);var b=rs[0].bounds;foreach(var r in rs)b.Encapsulate(r.bounds);return b;}
    static void Require(bool ok,string message){if(!ok)throw new InvalidOperationException(message);}
    static void Apply()
    {
        const string path="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity";
        var scene=SceneManager.GetActiveScene();Require(scene.path==path,"Expected corrected factory scene");
        var all=scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>(true)).ToArray();
        var floor=all.Single(t=>t.name.StartsWith("Floor_")&&t.parent&&t.parent.name.StartsWith("SMALL_FAB_"));
        var walls=new[]{"Rear_Wall","Front_Wall","Left_Wall","Right_Wall"}.Select(n=>all.Single(t=>t.name==n)).ToArray();
        var joints=all.Where(t=>t.name=="Rear_Panel_Joint"||t.name=="Stocker_Rear_Panel_Joint").ToArray();
        var old=floor.GetComponent<Renderer>().bounds;
        Require(Mathf.Abs(old.size.x-23.997818f)<.02f&&Mathf.Abs(old.size.z-15.6f)<.02f,"Unexpected room dimensions; refusing repeated trim");
        var grid=EditorSnapSettings.gridSize;
        Require(Mathf.Abs(grid.x-1)<.001f&&Mathf.Abs(grid.z-1)<.001f,"Scene grid is not the expected 1 m square: "+grid);
        float xMax=old.max.x-3*grid.x,zMin=old.min.z+2*grid.z;
        float width=xMax-old.min.x,depth=old.max.z-zMin,cx=(xMax+old.min.x)*.5f,cz=(old.max.z+zMin)*.5f;
        var changed=new HashSet<Transform>(walls.Concat(joints)){floor};
        Require(changed.All(t=>t.childCount==0&&t.rotation==Quaternion.identity&&t.parent.lossyScale==Vector3.one),"Unexpected shell hierarchy");
        var unchanged=all.Where(t=>!changed.Contains(t)).ToDictionary(t=>t,t=>t.localToWorldMatrix);
        // Confirm the requested empty strips contain neither equipment nor OHT track/supports.
        var equipment=scene.GetRootGameObjects().Select(o=>o.transform).Where(t=>t.GetComponentsInChildren<Renderer>(true).Length>0&&!t.name.StartsWith("SMALL_FAB_")&&!t.name.Contains("Volume")&&!t.name.Contains("Light")).ToArray();
        var clearance=new List<string>();
        foreach(var t in equipment){
            var visible=t.GetComponentsInChildren<Renderer>(true).Where(r=>r.enabled&&r.gameObject.activeInHierarchy&&!(r is ParticleSystemRenderer)&&!(r is LineRenderer)).ToArray();
            if(visible.Length==0)continue;var b=visible[0].bounds;foreach(var r in visible)b.Encapsulate(r.bounds);
            // World UI and camera/frustum decorations are not equipment footprints.
            if(t.GetComponent<Canvas>()||t.name.Contains("DASHBOARD")||t.name.Contains("CONTROL")||t.name.Contains("Camera"))continue;
            Require(b.max.x<=xMax+.01f&&b.min.z>=zMin-.01f,"Requested trim intersects "+t.name+" bounds="+b);
            clearance.Add(t.name+": right clearance="+(xMax-b.max.x).ToString("F3")+" m, AOI-side clearance="+(b.min.z-zMin).ToString("F3")+" m");
        }
        AssetDatabase.SaveAssets();Require(EditorSceneManager.SaveScene(scene),"Cannot save current scene");
        string backup="Tools/Backups/BeforeAoiIonFloorTrim-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);
        File.Copy(path,backup+"/FactoryBeforeFloorTrim.unity");File.Copy(path+".meta",backup+"/FactoryBeforeFloorTrim.unity.meta");
        foreach(var p in Directory.GetFiles("UserSettings/Layouts","*.dwlt"))File.Copy(p,Path.Combine(backup,Path.GetFileName(p)),true);
        File.WriteAllText(backup+"/RESTORE.txt","With Play stopped, restore FactoryBeforeFloorTrim.unity over "+path+"; retain existing scene .meta. Layouts backed up separately. Gateway records untouched.\n");
        var original=changed.ToDictionary(t=>t,t=>(t.localPosition,t.localScale,t.name));
        Undo.RecordObjects(changed.Cast<UnityEngine.Object>().ToArray(),"Trim AOI side two grid cells and ion side three grid cells");
        try{
            var p=floor.position;p.x=cx;p.z=cz;floor.position=p;var s=floor.localScale;s.x*=width/old.size.x;s.z*=depth/old.size.z;floor.localScale=s;
            floor.name="Floor_"+width.ToString("F2",System.Globalization.CultureInfo.InvariantCulture)+"x"+depth.ToString("F1",System.Globalization.CultureInfo.InvariantCulture)+"m";
            foreach(var t in walls){p=t.position;s=t.localScale;
                if(t.name=="Rear_Wall"||t.name=="Front_Wall"){p.x=cx;s.x*=width/old.size.x;if(t.name=="Front_Wall")p.z=zMin;}
                else{p.z=cz;s.z*=depth/old.size.z;if(t.name=="Right_Wall")p.x=xMax;}
                t.position=p;t.localScale=s;
            }
            foreach(var t in joints){p=t.position;p.x=old.min.x+(p.x-old.min.x)*width/old.size.x;t.position=p;}
            foreach(var pair in unchanged)Require(pair.Key.localToWorldMatrix==pair.Value,"Unrelated transform moved: "+pair.Key.name);
            var final=floor.GetComponent<Renderer>().bounds;
            Require(Mathf.Abs(final.min.x-old.min.x)<.002f&&Mathf.Abs(final.max.z-old.max.z)<.002f&&Mathf.Abs(final.max.x-xMax)<.002f&&Mathf.Abs(final.min.z-zMin)<.002f,"Floor edges do not match requested grid-cell reduction");
            foreach(var t in walls){var b=t.GetComponent<Renderer>().bounds;if(t.name=="Rear_Wall"||t.name=="Front_Wall")Require(Mathf.Abs(b.min.x-final.min.x)<.002f&&Mathf.Abs(b.max.x-final.max.x)<.002f,"Horizontal wall corner mismatch");else Require(Mathf.Abs(b.min.z-final.min.z)<.002f&&Mathf.Abs(b.max.z-final.max.z)<.002f,"Side wall corner mismatch");}
            foreach(var t in changed){EditorUtility.SetDirty(t);PrefabUtility.RecordPrefabInstancePropertyModifications(t);}
            EditorSceneManager.MarkSceneDirty(scene);Require(EditorSceneManager.SaveScene(scene),"Scene save failed");SceneView.RepaintAll();
            File.WriteAllText("TrimFactoryFloorEdges.result","FACTORY_AOI_ION_FLOOR_TRIM_OK\n"+DateTime.UtcNow.ToString("O")+"\nBackup: "+backup+"\nGrid: "+grid+"\nAOI side: 2 cells / "+(zMin-old.min.z).ToString("F3")+" m\nIon side: 3 cells / "+(old.max.x-xMax).ToString("F3")+" m\nFloor dimensions: "+final.size.ToString("F3")+"\nUnchanged transforms (including equipment, OHT, all cameras): "+unchanged.Count+"\nWall corners align. Editor layout and Game settings untouched. Play off. Scene saved. No server requests.\n"+string.Join("\n",clearance));
        }catch{foreach(var pair in original){pair.Key.localPosition=pair.Value.Item1;pair.Key.localScale=pair.Value.Item2;pair.Key.name=pair.Value.Item3;}EditorSceneManager.MarkSceneDirty(scene);throw;}
    }
}
#endif
