#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad] public static class OhtRailUprightChecks
{
    [Serializable] class Layout {public Vector3[] points;}
    static float legacyMinimumUp;
    static OhtRailUprightChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string error){if(!ok)throw new Exception(error);}
    static void Set(object o,string name,object value)=>o.GetType().GetField(name,BindingFlags.NonPublic|BindingFlags.Instance).SetValue(o,value);
    static void Tick()
    {
        if(!File.Exists("OhtRailUprightCheck.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("OhtRailUprightCheck.once");
        try{int count=Run();File.WriteAllText("OhtRailUprightCheck.result","OHT_RAIL_UPRIGHT_OK\n"+DateTime.UtcNow.ToString("O")+"\nActual OhtFabCycle.Pose / "+count+" samples around entire loop including reverse straight, corners and seam / original hanging lift and virtual loaded FOUP remain below rail / no production scene changes or network requests\nLegacy FromToRotation minimum up dot: "+legacyMinimumUp.ToString("F6"));}
        catch(Exception e){File.WriteAllText("OhtRailUprightCheck.result","FAILED: "+e);Debug.LogException(e);}
    }
    [MenuItem("MOSFET/OHT/Check upright rail loop (offline)")] public static int Run()
    {
        var source=UnityEngine.Object.FindAnyObjectByType<OhtFabCycle>();Check(source&&source.route&&source.carrier&&source.lift,"Open the factory scene with OHT");
        var points=JsonUtility.FromJson<Layout>(source.route.text).points;Check(points.Length>100,"Route missing");
        var lengths=new float[points.Length+1];for(int i=0;i<points.Length;i++)lengths[i+1]=lengths[i]+Vector3.Distance(points[i],points[(i+1)%points.Length]);
        var root=new GameObject("OHT upright offline probe"){hideFlags=HideFlags.HideAndDontSave};root.SetActive(false);
        try
        {
            var test=root.AddComponent<OhtFabCycle>();test.carrier=root.transform;
            var baseline=source.carrier.rotation;Set(test,"points",points);Set(test,"lengths",lengths);Set(test,"carrierRotation",baseline);
            var pose=typeof(OhtFabCycle).GetMethod("Pose",BindingFlags.NonPublic|BindingFlags.Instance);
            var liftOffset=Quaternion.Inverse(baseline)*(source.lift.position-source.carrier.position);
            Check((baseline*liftOffset).y<0,"Lift is not below carrier in source scene");
            var foupOffset=Quaternion.Inverse(baseline)*new Vector3(0,-.65f,0);
            int samples=0;legacyMinimumUp=1;
            for(int i=0;i<points.Length;i++)for(int part=0;part<4;part++)
            {
                float distance=Mathf.Lerp(lengths[i],lengths[i+1],part*.25f);pose.Invoke(test,new object[]{distance});
                var turn=test.carrier.rotation*Quaternion.Inverse(baseline);
                Check(Vector3.Dot(turn*Vector3.up,Vector3.up)>.99999f,"OHT pitched or rolled at segment "+i);
                Check(Mathf.Abs((test.carrier.rotation*liftOffset).y-(baseline*liftOffset).y)<.0001f,"Hanging lift crossed rail at segment "+i);
                Check((test.carrier.rotation*foupOffset).y<-.649f,"FOUP rose above rail at segment "+i);
                var legacy=Quaternion.FromToRotation(Vector3.right,(points[(i+1)%points.Length]-points[i]).normalized);
                legacyMinimumUp=Mathf.Min(legacyMinimumUp,Vector3.Dot(legacy*Vector3.up,Vector3.up));
                var expected=Vector3.Lerp(points[i],points[(i+1)%points.Length],part*.25f);
                Check(Vector3.Distance(test.carrier.position,expected)<.0001f,"Rail position changed at segment "+i);samples++;
            }
            foreach(float d in new[]{-0.001f,0f,lengths[lengths.Length-1],lengths[lengths.Length-1]+.001f})pose.Invoke(test,new object[]{d});
            var reversed=OhtFabCycle.RailRotation(Vector3.left,baseline)*Quaternion.Inverse(baseline);
            Check(Vector3.Dot(reversed*Vector3.right,Vector3.left)>.99999f&&Vector3.Dot(reversed*Vector3.up,Vector3.up)>.99999f,"Reverse direction flips payload");
            return samples;
        }
        finally{UnityEngine.Object.DestroyImmediate(root);}
    }
}
#endif
