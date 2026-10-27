#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
public static class OhtRailSurvey
{
    [Serializable]public class Port {public string id,node,equipment;public Vector3 position;}
    [Serializable]public class Obstacle {public string name;public Vector3 min,max;}
    [Serializable]public class Layout {public string scene;public Port[] ports;public Obstacle[] equipment;public Vector3 floorMin,floorMax;public float maxEquipmentHeight;}
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Tick;EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(!File.Exists("OhtRailSurvey.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("OhtRailSurvey.once");try{Survey();}catch(Exception e){File.WriteAllText("OhtRailSurvey.result",e.ToString());Debug.LogException(e);}
    }
    static Transform Find(GameObject obj,string n)=>obj.GetComponentsInChildren<Transform>(true).First(t=>t.name==n);
    public static Bounds BoundsOf(GameObject obj)
    {
        var rs=obj.GetComponentsInChildren<Renderer>().Where(r=>r.enabled&&r.gameObject.activeInHierarchy).ToArray();var b=rs.First().bounds;foreach(var r in rs)b.Encapsulate(r.bounds);return b;
    }
    [MenuItem("MOSFET Factory/Survey OHT Dock Positions")]
    public static void Survey()
    {
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();if(!scene.path.EndsWith("MOSFETSmallFab_Corrected.unity"))throw new Exception("Open corrected cleanroom scene.");
        var names=new[]{"Mini_Stocker_6Slot","Oxidation_System_Integrated","Ellipsometer_System","Ion_Implanter"};
        var nodes=new[]{"FOUP_DockPoint","OX_LOADPORT_01_Dock","FOUP_Dock_01","FOUP_Dock_02"};
        var ports=names.Select((n,i)=>new Port{id=new[]{"STOCKER_IO","OX_LOADPORT","ELLIP_LOADPORT","IMP_LOADPORT"}[i],equipment=n,node=nodes[i],position=Find(GameObject.Find(n),nodes[i]).position}).ToArray();
        var all=names.Select(GameObject.Find).ToArray();var floor=scene.GetRootGameObjects().First(o=>o.name.StartsWith("SMALL_FAB_")).GetComponentsInChildren<Transform>(true).First(t=>t.name.StartsWith("Floor_")).GetComponent<Renderer>().bounds;
        var data=new Layout{scene=scene.path,ports=ports,equipment=all.Select(o=>{var b=BoundsOf(o);return new Obstacle{name=o.name,min=b.min,max=b.max};}).ToArray(),floorMin=floor.min,floorMax=floor.max,maxEquipmentHeight=all.Max(o=>BoundsOf(o).max.y)};
        File.WriteAllText("Blender/OHT_Unity_layout.json",JsonUtility.ToJson(data,true));File.WriteAllText("OhtRailSurvey.result","OHT_DOCK_SURVEY_OK");
    }
}
#endif
