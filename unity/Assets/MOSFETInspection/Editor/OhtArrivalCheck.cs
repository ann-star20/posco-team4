#if UNITY_EDITOR
using System;
using System.Collections;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad] public static class OhtArrivalCheck
{
    const BindingFlags Flags=BindingFlags.Instance|BindingFlags.NonPublic;
    static OhtArrivalCheck(){EditorApplication.update+=Tick;}
    static void Set(OhtFabCycle o,string field,object value)=>typeof(OhtFabCycle).GetField(field,Flags).SetValue(o,value);
    static IEnumerator Travel(OhtFabCycle o,int port)=>(IEnumerator)typeof(OhtFabCycle).GetMethod("Travel",Flags).Invoke(o,new object[]{port});
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(!File.Exists("OhtArrivalCheck.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("OhtArrivalCheck.once");
        var root=new GameObject("Offline OHT arrival check"){hideFlags=HideFlags.HideAndDontSave};root.SetActive(false);
        try
        {
            var o=root.AddComponent<OhtFabCycle>();o.carrier=new GameObject("carrier").transform;o.carrier.SetParent(root.transform);
            o.lift=new GameObject("lift").transform;o.lift.SetParent(o.carrier,false);o.validationDelta=.1f;
            Set(o,"points",new[]{new Vector3(0,5,0),new Vector3(1,5,0),new Vector3(1,5,1),new Vector3(0,5,1)});
            Set(o,"lengths",new[]{0f,1f,2f,3f,4f});Set(o,"stopDistances",new[]{1f,2f,3f,0f});Set(o,"carrierRotation",Quaternion.identity);
            foreach(float position in new[]{1f,1.0001f,.9999f})
            {Set(o,"distance",position);Check(!Travel(o,0).MoveNext(),"Already at pickup stop, but Travel requested a full lap");}
            Set(o,"distance",3.9999f);Check(!Travel(o,3).MoveNext(),"Route seam incorrectly requested a lap");
            Set(o,"distance",1f);var moving=Travel(o,1);Check(moving.MoveNext(),"Different destination no longer travels");(moving as IDisposable)?.Dispose();
            File.WriteAllText("OhtArrivalCheck.result","OHT_SAME_STOP_NO_LAP_OK\n"+DateTime.UtcNow.ToString("O")+"\nActual Travel iterator: same stop, both float offsets and loop seam finish without movement; different stop still travels.");
        }
        catch(Exception e){File.WriteAllText("OhtArrivalCheck.result","FAILED\n"+e);Debug.LogException(e);}
        finally{UnityEngine.Object.DestroyImmediate(root);}
    }
}
#endif
