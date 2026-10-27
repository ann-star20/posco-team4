#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad] public static class OhtPickupVisibilityCheck
{
    const string Key="OhtPickupVisibilityCheckPhase";
    const BindingFlags Flags=BindingFlags.Instance|BindingFlags.NonPublic;
    static OhtPickupVisibilityCheck(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static object Call(OhtFabCycle o,string name,params object[] args)=>typeof(OhtFabCycle).GetMethod(name,Flags).Invoke(o,args);
    static void Set(OhtFabCycle o,string name,object value)=>typeof(OhtFabCycle).GetField(name,Flags).SetValue(o,value);
    static void Drive(IEnumerator iterator,Action visible)
    {
        var stack=new Stack<IEnumerator>();stack.Push(iterator);int ticks=0;
        while(stack.Count>0)
        {
            Check(++ticks<10000,"Pickup check timed out");
            var top=stack.Peek();if(!top.MoveNext()){stack.Pop();continue;}
            visible();if(top.Current is IEnumerator child)stack.Push(child);
        }
    }
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("OhtPickupVisibility.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("OhtPickupVisibility.once");var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
                Check(EditorSceneManager.SaveScene(scene),"Save before runtime test failed");SessionState.SetString(Key+"Scene",scene.path);
                SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                var o=UnityEngine.Object.FindAnyObjectByType<OhtFabCycle>();Check(o&&!o.failed&&!o.Running,"OHT not idle");
                o.enabled=false;o.validationDelta=.25f;o.ellipsometer.completed=o.implanter.completed=true;
                for(int port=2;port<=3;port++)
                {
                    Set(o,"running",false);Set(o,"held",false);o.foup.gameObject.SetActive(false);
                    o.stocker.location=StockerCycle.CarrierLocation.Stored;o.stocker.occupied[o.stocker.reservedSlot]=true;
                    var recovery=(IEnumerator)Call(o,"RecoverStandalone",port);
                    Check(recovery.MoveNext()&&recovery.Current is IEnumerator,"Recovery did not start travel");
                    Action dockVisible=()=>Check(o.stationCarriers[port].gameObject.activeInHierarchy,"Completed FOUP disappeared before pickup at port "+port);
                    dockVisible();Drive((IEnumerator)recovery.Current,dockVisible);
                    var pick=(IEnumerator)Call(o,"Pick",port,true);
                    Check(pick.MoveNext(),"Pickup did not start");
                    Action payloadVisible=()=>Check(!o.stationCarriers[port].gameObject.activeSelf&&o.foup.gameObject.activeInHierarchy,"FOUP handoff gap or duplicate at port "+port);
                    payloadVisible();if(pick.Current is IEnumerator first)Drive(first,payloadVisible);Drive(pick,payloadVisible);
                    Check(o.Held&&Vector3.Distance(o.attachPoint.position,o.foupGrip.position)<.002f,"OHT grip failed");
                    (recovery as IDisposable)?.Dispose();
                }
                File.WriteAllText("OhtPickupVisibility.result","OHT_PICKUP_VISIBILITY_OK\n"+DateTime.UtcNow.ToString("O")+"\nActual ellipsometer and ion RecoverStandalone approach + full Pick/hoist passed. Dock FOUP stayed active for every approach step; same-step swap to one visible transport FOUP; grip alignment passed. No inspection or server requests.");
                SessionState.SetInt(Key,2);EditorApplication.isPlaying=false;return;
            }
            if(phase==2&&!EditorApplication.isPlayingOrWillChangePlaymode)
            {EditorSceneManager.OpenScene(SessionState.GetString(Key+"Scene",""));SessionState.SetInt(Key,0);}
        }
        catch(Exception e)
        {
            File.WriteAllText("OhtPickupVisibility.result","FAILED\n"+e);Debug.LogException(e);
            SessionState.SetInt(Key,2);EditorApplication.isPlaying=false;
        }
    }
}
#endif
