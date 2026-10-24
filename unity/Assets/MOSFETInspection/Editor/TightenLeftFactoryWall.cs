#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

[InitializeOnLoad] public static class TightenLeftFactoryWall
{
    static TightenLeftFactoryWall(){EditorApplication.update+=Check;}
    static void Check()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(File.Exists("TightenLeftFactoryWall.once")){
            if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
            File.Delete("TightenLeftFactoryWall.once");
            try{Apply();}catch(Exception e){File.WriteAllText("TightenLeftFactoryWall.result","FAILED\n"+e);Debug.LogException(e);}
            return;
        }
        if(!File.Exists("TightenLeftFactoryWallSurvey.once"))return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("TightenLeftFactoryWallSurvey.once");
        try{
            var all=SceneManager.GetActiveScene().GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>(true)).ToArray();
            var lines=all.Where(t=>t.name.Contains("Wall")||t.name.StartsWith("Floor_")||t.name.Contains("Joint")||t.name.IndexOf("stocker",StringComparison.OrdinalIgnoreCase)>=0).Select(t=>{
                var r=t.GetComponent<Renderer>();var rs=t.GetComponentsInChildren<Renderer>(true);var b=rs.Length>0?rs[0].bounds:new Bounds(t.position,Vector3.zero);foreach(var item in rs)b.Encapsulate(item.bounds);
                return t.name+" | parent="+(t.parent?t.parent.name:"")+" | pos="+t.position.ToString("F3")+" | scale="+t.localScale.ToString("F3")+" | min="+b.min.ToString("F3")+" | max="+b.max.ToString("F3")+" | children="+t.childCount;
            });
            File.WriteAllLines("TightenLeftFactoryWallSurvey.result",lines);
        }catch(Exception e){File.WriteAllText("TightenLeftFactoryWallSurvey.result",e.ToString());}
    }
    static void Apply()
    {
        const string path="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity";
        var scene=SceneManager.GetActiveScene();if(scene.path!=path)throw new Exception("Expected corrected factory scene");
        var all=scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>(true)).ToArray();
        var floor=all.Single(t=>t.name.StartsWith("Floor_")&&t.parent&&t.parent.name.StartsWith("SMALL_FAB_"));
        var left=all.Single(t=>t.name=="Left_Wall");var rear=all.Single(t=>t.name=="Rear_Wall");var front=all.Single(t=>t.name=="Front_Wall");
        var stocker=all.Single(t=>t.name=="Mini_Stocker_6Slot");var rs=stocker.GetComponentsInChildren<Renderer>(true);var sb=rs[0].bounds;foreach(var r in rs)sb.Encapsulate(r.bounds);
        var old=floor.GetComponent<Renderer>().bounds;float oldLeft=left.position.x;
        float target=sb.min.x-.60f-left.GetComponent<Renderer>().bounds.size.x*.5f;
        if(target-oldLeft<.1f)throw new Exception("Left wall already close to stocker; refusing repeated resize");
        var joints=all.Where(t=>t.name=="Rear_Panel_Joint"||t.name=="Stocker_Rear_Panel_Joint").ToArray();
        var camera=all.Single(t=>t.name=="FAB_OVERVIEW_CAMERA");
        var changed=new HashSet<Transform>(joints){floor,left,rear,front,camera};
        if(changed.Any(t=>t.childCount!=0||t.parent&&t.parent.lossyScale!=Vector3.one||t.rotation!=Quaternion.identity&&t!=camera))throw new Exception("Unexpected shell hierarchy or axes");
        var unchanged=all.Where(t=>!changed.Contains(t)).ToDictionary(t=>t,t=>t.localToWorldMatrix);
        AssetDatabase.SaveAssets();if(!EditorSceneManager.SaveScene(scene))throw new Exception("Cannot save baseline");
        string backup="Tools/Backups/BeforeLeftWallTightening-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);
        File.Copy(path,backup+"/FactoryBeforeLeftWall.unity");File.Copy(path+".meta",backup+"/FactoryBeforeLeftWall.unity.meta");
        File.WriteAllText(backup+"/RESTORE.txt","Restore FactoryBeforeLeftWall.unity over "+path+" with Unity Play stopped. Keep the existing scene .meta. No equipment or Gateway data changes.\n");
        Undo.RecordObjects(changed.Cast<UnityEngine.Object>().ToArray(),"Move left factory wall closer to stocker");
        float width=old.max.x-target,centre=(old.max.x+target)*.5f,ratio=width/old.size.x;
        var p=left.position;p.x=target;left.position=p;
        foreach(var t in new[]{floor,rear,front}){p=t.position;p.x=centre;t.position=p;var s=t.localScale;s.x*=ratio;t.localScale=s;}
        floor.name="Floor_"+width.ToString("F2",System.Globalization.CultureInfo.InvariantCulture)+"x"+old.size.z.ToString("F1",System.Globalization.CultureInfo.InvariantCulture)+"m";
        foreach(var t in joints){p=t.position;p.x=target+(p.x-old.min.x)*ratio;t.position=p;}
        var room=floor.GetComponent<Renderer>().bounds;foreach(var t in new[]{left,rear,front})room.Encapsulate(t.GetComponent<Renderer>().bounds);
        // Keep the overview angle, framing the resized room at the normal 16:9 demo aspect.
        var cam=camera.GetComponent<Camera>();var inverse=Quaternion.Inverse(camera.rotation);float tan=Mathf.Tan(cam.fieldOfView*Mathf.Deg2Rad*.5f),distance=1;
        for(int i=0;i<8;i++){var corner=new Vector3((i&1)==0?room.min.x:room.max.x,(i&2)==0?room.min.y:room.max.y,(i&4)==0?room.min.z:room.max.z);var v=inverse*(corner-room.center);distance=Mathf.Max(distance,Mathf.Abs(v.y)/tan-v.z,Mathf.Abs(v.x)/(tan*(16f/9f))-v.z);}
        camera.position=room.center-camera.forward*(distance*1.06f);
        foreach(var pair in unchanged)if(pair.Key.localToWorldMatrix!=pair.Value)throw new Exception("Unrelated transform moved: "+pair.Key.name);
        var final=floor.GetComponent<Renderer>().bounds;
        if(Mathf.Abs(final.max.x-old.max.x)>.002f||Mathf.Abs(final.min.x-target)>.002f||Mathf.Abs(final.size.z-old.size.z)>.002f)throw new Exception("Floor boundary mismatch");
        foreach(var t in new[]{rear,front}){var b=t.GetComponent<Renderer>().bounds;if(Mathf.Abs(b.min.x-target)>.002f||Mathf.Abs(b.max.x-old.max.x)>.002f)throw new Exception("Wall corner mismatch");}
        float gap=sb.min.x-left.GetComponent<Renderer>().bounds.max.x;if(Mathf.Abs(gap-.60f)>.002f)throw new Exception("Stocker clearance mismatch");
        foreach(var t in changed){EditorUtility.SetDirty(t);PrefabUtility.RecordPrefabInstancePropertyModifications(t);}
        EditorSceneManager.MarkSceneDirty(scene);if(!EditorSceneManager.SaveScene(scene))throw new Exception("Scene save failed");
        foreach(SceneView view in SceneView.sceneViews)view.LookAt(room.center,view.rotation,Mathf.Max(room.size.x,room.size.z)*.7f);
        SceneView.RepaintAll();
        File.WriteAllText("TightenLeftFactoryWall.result","LEFT_FACTORY_WALL_TIGHTENED_OK\n"+DateTime.UtcNow.ToString("O")+"\nBackup: "+backup+"\nWall moved inward: "+(target-oldLeft).ToString("F3")+" m\nStocker clearance: "+gap.ToString("F3")+" m\nFloor: "+final.size.ToString("F3")+"\nUnchanged equipment/OHT/other transforms: "+unchanged.Count+"\nFloor and front/rear wall boundaries align. Right boundary and floor depth unchanged. Scene saved. No Play test or server request.");
    }
}
#endif
