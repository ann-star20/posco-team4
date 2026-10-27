#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class OhtStartChecks
{
    static OhtStartChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Set(object target,string field,bool value)=>target.GetType().GetField(field,BindingFlags.Instance|BindingFlags.NonPublic).SetValue(target,value);
    static void Tick()
    {
        if(!File.Exists("OhtStartCheck.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("OhtStartCheck.once");
        try{Run();File.WriteAllText("OhtStartCheck.result","OHT_START_GUARDS_OK\n"+DateTime.UtcNow.ToString("O")+"\nActual OhtFabCycle startup checks: HOLD rejection preserves HOLD / exact equipment-busy reason / stocker error / initialized-ready state / no scene or network requests");}
        catch(Exception e){File.WriteAllText("OhtStartCheck.result","FAILED: "+e);Debug.LogException(e);}
    }
    [MenuItem("MOSFET/OHT/Check start conditions (offline)")]
    public static void Run()
    {
        var root=new GameObject("OHT start checks"){hideFlags=HideFlags.HideAndDontSave};root.SetActive(false);
        try
        {
            var oht=root.AddComponent<OhtFabCycle>();oht.oxidation=root.AddComponent<IntegratedOxidationCycle>();oht.ellipsometer=root.AddComponent<EllipsometerCycle>();oht.implanter=root.AddComponent<IonImplantCycle>();oht.stocker=root.AddComponent<StockerCycle>();
            Check(oht.StartBlockReason.Contains("초기화"),"Uninitialized OHT gives no reason");
            Set(oht,"initialized",true);Check(string.IsNullOrEmpty(oht.StartBlockReason),"Idle equipment cannot start");
            oht.ellipsometer.lotId="LOT-HOLD-TEST";oht.ellipsometer.lotHeld=true;
            Check(oht.StartBlockReason.Contains("HOLD")&&oht.StartBlockReason.Contains("LOT-HOLD-TEST"),"HOLD reason missing LOT");
            oht.StartCycle();Check(!oht.Running&&oht.ellipsometer.lotHeld&&oht.status.Contains("HOLD"),"Start bypassed/cleared HOLD");
            oht.ellipsometer.lotHeld=false;
            foreach(var target in new MonoBehaviour[]{oht.oxidation,oht.ellipsometer,oht.implanter,oht.stocker})
            {
                Set(target,"running",true);Check(!string.IsNullOrEmpty(oht.StartBlockReason),"Busy equipment not blocked");
                oht.StartCycle();Check(!oht.Running&&oht.status.Contains("START BLOCKED"),"Busy equipment started OHT");Set(target,"running",false);
            }
            oht.stocker.failed=true;Check(oht.StartBlockReason.Contains("스토커"),"Stocker error reason absent");oht.stocker.failed=false;
            Check(string.IsNullOrEmpty(oht.StartBlockReason),"Conditions did not recover after equipment idle");
            Set(oht,"initialized",false);
        }
        finally{UnityEngine.Object.DestroyImmediate(root);}
    }
}
#endif
