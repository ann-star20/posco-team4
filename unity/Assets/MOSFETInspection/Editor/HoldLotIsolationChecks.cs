#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;
[InitializeOnLoad] public static class HoldLotIsolationChecks
{
    static HoldLotIsolationChecks(){EditorApplication.update+=Tick;}
    static void Check(bool value,string error){if(!value)throw new Exception(error);}
    static void Tick()
    {
        if(!File.Exists("HoldLotIsolationCheck.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("HoldLotIsolationCheck.once");
        try{Run();File.WriteAllText("HoldLotIsolationCheck.result","HOLD_LOT_ISOLATION_POLICY_OK\n"+DateTime.UtcNow.ToString("O"));}
        catch(Exception e){File.WriteAllText("HoldLotIsolationCheck.result","FAILED: "+e);Debug.LogException(e);}
    }
    [MenuItem("MOSFET/OHT/Check HOLD isolation (offline)")] public static void Run()
    {
        var root=new GameObject("Hold isolation offline"){hideFlags=HideFlags.HideAndDontSave};root.SetActive(false);
        try
        {
            var o=root.AddComponent<OhtFabCycle>();o.ellipsometer=root.AddComponent<EllipsometerCycle>();o.implanter=root.AddComponent<IonImplantCycle>();o.stocker=root.AddComponent<StockerCycle>();
            o.ellipsometer.completed=true;o.ellipsometer.lotHeld=true;
            Check(o.NeedsQuarantine(2),"Film HOLD ignored");
            Check(o.ellipsometer.SafeToUnload,"Closed completed film cannot unload HOLD");
            o.implanter.completed=true;o.implanter.dose=1;
            Check(o.NeedsQuarantine(3),"Implant NG ignored");
            Check(o.implanter.SafeToUnload,"Closed completed implant cannot unload");
            o.implanter.failed=true;Check(!o.implanter.SafeToUnload,"Failed tool allowed pickup");
            var s=o.stocker;s.heldInspections=new string[6];s.heldInspections[0]="old-film";s.occupied=new[]{true,false,false,true,true,false};
            Check(s.NextFreeSlot==1,"New carrier overwrites held slot");
            Check(s.IsHeldSlot(0)&&!s.IsHeldSlot(1),"Hold inventory not isolated");
            Check(!s.CanDispatchReserved,"Held carrier can dispatch to production");
            s.reservedSlot=1;Check(!s.CanDispatchReserved,"Empty slot can dispatch");
            s.occupied[1]=true;Check(s.CanDispatchReserved,"Ready carrier blocked by another HOLD");
            s.occupied=new[]{true,true,true,true,true,true};Check(s.NextFreeSlot==-1,"Full stocker overwrites occupied slot");
            o.ellipsometer.lotHeld=true;Check(!o.ellipsometer.CanProceed,"Quarantine bypassed downstream gate");
        }
        finally{UnityEngine.Object.DestroyImmediate(root);}
    }
}
#endif
