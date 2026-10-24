#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

[InitializeOnLoad] public static class ExpandFactoryRoom
{
    const string ScenePath="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity";
    const string Latest="Tools/Backups/FactoryRoomBaseline.txt";
    static ExpandFactoryRoom(){EditorApplication.update+=Check;}
    static void Check()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        string marker=File.Exists("RestoreFactoryRoom.once")?"RestoreFactoryRoom.once":File.Exists("ExpandFactoryRoom.once")?"ExpandFactoryRoom.once":null;
        if(marker==null)return;File.Delete(marker);
        try{if(marker.StartsWith("Restore"))Restore();else Expand();}
        catch(Exception e){File.WriteAllText("ExpandFactoryRoom.result","FAILED\n"+e);Debug.LogException(e);}
    }
    static string Backup(Scene scene)
    {
        AssetDatabase.SaveAssets();if(!EditorSceneManager.SaveScene(scene))throw new IOException("Could not save current scene before backup");
        string dir="Tools/Backups/BeforeRoomExpansion-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(dir);
        File.Copy(ScenePath,Path.Combine(dir,"FactoryBeforeExpansion.unity"));
        File.Copy(ScenePath+".meta",Path.Combine(dir,"FactoryBeforeExpansion.unity.meta"));
        foreach(string root in new[]{"Assets/MOSFETInspection","ProjectSettings","Packages"})
        foreach(string source in Directory.GetFiles(root,"*",SearchOption.AllDirectories))
        {
            string ext=Path.GetExtension(source).ToLowerInvariant();
            if(root=="Assets/MOSFETInspection"&&ext!=".cs"&&ext!=".mat"&&ext!=".asset"&&ext!=".json"&&!(ext==".meta"&&source.EndsWith(".cs.meta")))continue;
            string dest=Path.Combine(dir,source);Directory.CreateDirectory(Path.GetDirectoryName(dest));File.Copy(source,dest,true);
        }
        File.WriteAllText(Path.Combine(dir,"RESTORE.txt"),"Expansion baseline: saved open factory scene, inspection scripts/materials/settings and Packages. Existing model files remain in this project.\nRestore only the room layout with Unity menu MOSFET Factory/Room/Restore before expansion.\nOriginal scene: "+ScenePath+"\nThe restore menu first saves a copy of the expanded scene, then restores FactoryBeforeExpansion.unity.\nGateway DB and server jobs are never deleted or changed.\nScene background: white; Game camera backgrounds are included in the saved scene.");
        File.WriteAllText(Latest,Path.GetFullPath(dir));return dir;
    }
    static void Expand()
    {
        var scene=SceneManager.GetActiveScene();if(scene.path!=ScenePath)throw new InvalidOperationException("Open the corrected factory scene first");
        var all=scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>(true)).ToArray();
        var floor=all.Single(t=>t.name.StartsWith("Floor_")&&t.parent&&t.parent.name.StartsWith("SMALL_FAB_"));
        if(floor.rotation!=Quaternion.identity||floor.parent.lossyScale!=Vector3.one)throw new InvalidOperationException("Factory shell axes or scale changed");
        var oldSize=floor.GetComponent<Renderer>().bounds.size;
        if(Mathf.Abs(oldSize.x-21)>.02f||Mathf.Abs(oldSize.z-12)>.02f)throw new InvalidOperationException("Expected 21 x 12 m baseline; expansion is not applied twice");
        var walls=new[]{"Rear_Wall","Front_Wall","Left_Wall","Right_Wall"}.Select(n=>all.Single(t=>t.name==n)).ToArray();
        var joints=all.Where(t=>t.name=="Rear_Panel_Joint"||t.name=="Stocker_Rear_Panel_Joint").ToArray();
        var anchors=all.Where(t=>t.name.StartsWith("Rear_Wall_Anchor_")).ToArray();
        var ties=all.Where(t=>t.name.StartsWith("Rear_Wall_Tie_")).ToArray();
        var overview=all.Single(t=>t.name=="FAB_OVERVIEW_CAMERA");
        var changed=new HashSet<Transform>(walls.Concat(joints).Concat(anchors).Concat(ties)){floor,overview};
        if(changed.Any(t=>t.childCount!=0))throw new InvalidOperationException("Expected leaf geometry/camera; refusing to move dependent objects");
        var original=all.Where(t=>!changed.Contains(t)).ToDictionary(t=>t,t=>t.localToWorldMatrix);
        string backup=Backup(scene);const float factor=1.3f;
        Undo.RecordObjects(changed.Cast<UnityEngine.Object>().ToArray(),"Expand factory floor and walls");
        var centre=floor.GetComponent<Renderer>().bounds.center;var size=floor.localScale;size.x*=factor;size.z*=factor;floor.localScale=size;
        floor.name="Floor_27.3x15.6m";
        foreach(var wall in walls)
        {
            var p=wall.position;var s=wall.localScale;
            if(wall.name=="Rear_Wall"||wall.name=="Front_Wall"){s.x*=factor;p.z=centre.z+(wall.name=="Rear_Wall"?1:-1)*oldSize.z*factor*.5f;}
            else{s.z*=factor;p.x=centre.x+(wall.name=="Right_Wall"?1:-1)*oldSize.x*factor*.5f;}
            wall.localScale=s;wall.position=p;
        }
        foreach(var joint in joints){var p=joint.position;p.x=centre.x+(p.x-centre.x)*factor;p.z+=oldSize.z*(factor-1)*.5f;joint.position=p;}
        float rearDelta=oldSize.z*(factor-1)*.5f;
        foreach(var anchor in anchors)anchor.position+=Vector3.forward*rearDelta;
        foreach(var tie in ties)
        {
            var renderer=tie.GetComponent<Renderer>();var before=renderer.bounds;
            var direction=tie.InverseTransformDirection(Vector3.forward);int axis=Mathf.Abs(direction.x)>.99f?0:Mathf.Abs(direction.y)>.99f?1:Mathf.Abs(direction.z)>.99f?2:-1;
            if(axis<0||before.size.z<.001f)throw new InvalidOperationException("Wall tie axis cannot be extended safely");
            var scale=tie.localScale;scale[axis]*=(before.size.z+rearDelta)/before.size.z;tie.localScale=scale;
            tie.position+=before.center+Vector3.forward*(rearDelta*.5f)-renderer.bounds.center;
            if(Mathf.Abs(renderer.bounds.min.z-before.min.z)>.002f||Mathf.Abs(renderer.bounds.max.z-before.max.z-rearDelta)>.002f)throw new InvalidOperationException("Wall tie endpoints changed incorrectly");
        }
        var bounds=floor.GetComponent<Renderer>().bounds;foreach(var wall in walls)bounds.Encapsulate(wall.GetComponent<Renderer>().bounds);
        var cam=overview.GetComponent<Camera>();var inverse=Quaternion.Inverse(cam.transform.rotation);float tan=Mathf.Tan(cam.fieldOfView*Mathf.Deg2Rad*.5f),distance=1;
        for(int i=0;i<8;i++){var corner=new Vector3((i&1)==0?bounds.min.x:bounds.max.x,(i&2)==0?bounds.min.y:bounds.max.y,(i&4)==0?bounds.min.z:bounds.max.z);var v=inverse*(corner-bounds.center);distance=Mathf.Max(distance,Mathf.Abs(v.y)/tan-v.z,Mathf.Abs(v.x)/(tan*cam.aspect)-v.z);}
        cam.transform.position=bounds.center-cam.transform.forward*(distance*1.06f);
        foreach(var pair in original)if(pair.Key.localToWorldMatrix!=pair.Value)throw new InvalidOperationException("Unrelated object moved: "+pair.Key.name);
        var final=floor.GetComponent<Renderer>().bounds;
        if(Mathf.Abs(final.size.x-27.3f)>.02f||Mathf.Abs(final.size.z-15.6f)>.02f)throw new InvalidOperationException("Room dimensions incorrect");
        foreach(var t in changed){EditorUtility.SetDirty(t);PrefabUtility.RecordPrefabInstancePropertyModifications(t);}
        EditorSceneManager.MarkSceneDirty(scene);if(!EditorSceneManager.SaveScene(scene))throw new IOException("Expanded scene save failed");
        foreach(SceneView view in SceneView.sceneViews)view.LookAt(bounds.center,view.rotation,Mathf.Max(bounds.size.x,bounds.size.z)*.7f);
        SceneView.RepaintAll();
        File.WriteAllText("ExpandFactoryRoom.result","FACTORY_ROOM_EXPANDED_OK\n"+DateTime.UtcNow.ToString("O")+"\nBaseline: "+backup+"\nFloor: 21 x 12 -> 27.3 x 15.6 m\nWall height/thickness unchanged. Rear joints and wall mounts follow wall; ties extended with rail-side endpoints fixed. Overview camera reframed.\nUnchanged object matrices verified: "+original.Count+"\nEquipment, OHT rails and moving assemblies, loadports, dock targets, lights and detail cameras retain their transforms. No server requests.");
    }
    [MenuItem("MOSFET Factory/Room/Restore before expansion")]
    public static void Restore()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode)throw new InvalidOperationException("Stop Play before restoring");
        string dir=Path.GetFullPath(File.ReadAllText(Latest).Trim());
        if(!dir.StartsWith(Path.GetFullPath("Tools/Backups")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Invalid baseline path");
        string source=Path.Combine(dir,"FactoryBeforeExpansion.unity");if(!File.Exists(source))throw new FileNotFoundException("Baseline scene missing",source);
        var scene=SceneManager.GetActiveScene();if(scene.path!=ScenePath)throw new InvalidOperationException("Open the corrected factory scene first");
        if(!EditorSceneManager.SaveScene(scene))throw new IOException("Could not preserve current scene");
        File.Copy(ScenePath,Path.Combine(dir,"BeforeRestore-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".unity"));
        File.Copy(source,ScenePath,true);AssetDatabase.ImportAsset(ScenePath,ImportAssetOptions.ForceUpdate);EditorSceneManager.OpenScene(ScenePath,OpenSceneMode.Single);
        File.WriteAllText("ExpandFactoryRoom.result","FACTORY_ROOM_RESTORED_OK\nBaseline: "+dir);
    }
}
#endif
