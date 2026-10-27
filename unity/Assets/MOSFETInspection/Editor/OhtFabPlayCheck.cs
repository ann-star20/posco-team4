#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class OhtFabPlayCheck
{
    const string Key="OhtFab.PlayPhase";
    static OhtFabCycle test;
    static double deadline,after;
    static Vector3 frozen;
    static int oldPlacements;
    static OhtFabPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string reason){if(!ok)throw new Exception(reason);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("OhtFabPlay.once")||EditorApplication.isPlaying||EditorApplication.isPlayingOrWillChangePlaymode)return;
                try{File.Delete("OhtFabPlay.once");}catch(IOException){return;}
                SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                test=UnityEngine.Object.FindAnyObjectByType<OhtFabCycle>();Check(test&&!test.Running&&!test.failed,"OHT must wait for manual start");
                Check(test.overview.enabled,"Overview camera must be enabled at start");
                Check(test.stocker&&test.stocker.Stored&&test.stocker.OccupiedCount==3,"Stocker must start with carrier stored");
                Application.runInBackground=true;Time.timeScale=12;FactoryControlBar.Select(FactoryControlBar.Equipment.OHT);
                Check(test.oxidation.TransportAvailable&&test.ellipsometer.TransportAvailable&&test.implanter.TransportAvailable,"Idle OHT must allow individual equipment starts");
                for(int i=1;i<4;i++)Check(test.stationCarriers[i].gameObject.activeInHierarchy,"Individual demo FOUP is hidden");
                // Exercise the mechanisms directly; public start buttons now request OHT delivery.
                test.oxidation.StartCoroutine(test.oxidation.Cycle());test.ellipsometer.StartCoroutine(test.ellipsometer.Cycle());test.implanter.StartCoroutine(test.implanter.Cycle());
                Check(test.oxidation.Running&&test.ellipsometer.Running&&test.implanter.Running,"Individual equipment start failed");
                test.StartCycle();Check(!test.Running,"OHT took over a running individual demo");
                deadline=EditorApplication.timeSinceStartup+300;SessionState.SetInt(Key,11);
            }
            else if(phase==11)
            {
                Check(!test.oxidation.failed&&!test.ellipsometer.failed&&!test.implanter.failed,"Individual demo failed");
                if(test.oxidation.completed&&test.ellipsometer.completed&&test.implanter.completed)
                {
                    test.StartCycle();Check(test.Running,"OHT did not start after individual demos completed");
                    Check(!test.implanter.TransportAvailable,"Implant must wait for OHT arrival during continuous run");
                    SessionState.SetInt(Key,2);
                }
            }
            else if(phase==2&&test.status=="MOVING"&&test.Held)
            {
                test.ToggleCamera();test.TogglePause();frozen=test.carrier.position;after=EditorApplication.timeSinceStartup+.7;
                ScreenCapture.CaptureScreenshot("OHT_Animation_Moving.png");SessionState.SetInt(Key,3);
            }
            else if(phase==3&&EditorApplication.timeSinceStartup>after)
            {Check(Vector3.Distance(frozen,test.carrier.position)<.001f,"Paused carrier moved");Check(test.followCamera.enabled,"Follow camera not enabled");ScreenCapture.CaptureScreenshot("OHT_Animation_Moving.png");after=EditorApplication.timeSinceStartup+.5;SessionState.SetInt(Key,10);}
            else if(phase==10&&EditorApplication.timeSinceStartup>after)
            {test.ToggleCamera();test.TogglePause();SessionState.SetInt(Key,4);}
            else if(phase==4&&test.completed)
            {
                Check(test.placements==4&&test.completedRuns==1,"Full process route or return missing");
                Check(test.oxidation.TransportAvailable&&test.ellipsometer.TransportAvailable&&test.implanter.TransportAvailable,"Individual starts not restored after OHT completion");
                Check(test.oxidation.completed&&test.ellipsometer.CanProceed&&test.implanter.completed&&!test.implanter.AnyGateOpen,"Process completion missing");
                Check(!test.Held&&test.stocker.Stored&&Vector3.Distance(test.foupDock.position,test.stocker.slots[0].position)<.003f,"FOUP did not return to reserved storage slot");
                Check(test.stocker.outgoingRuns==1&&test.stocker.incomingRuns==1&&!test.stocker.DoorOpen,"Stocker dispatch/receipt incomplete");
                ScreenCapture.CaptureScreenshot("OHT_Animation_Complete.png");test.ellipsometer.demoHold=true;test.StartCycle();SessionState.SetInt(Key,5);
            }
            else if(phase==5&&test.status=="LOT HOLD / REVIEW REQUIRED")
            {
                Check(test.ellipsometer.lotHeld&&!test.implanter.Running&&!test.Held,"HOLD did not retain FOUP at metrology");
                Check(test.stocker.location==StockerCycle.CarrierLocation.InTransit&&!test.stocker.occupied[0],"HOLD incorrectly returned carrier to storage");
                frozen=test.carrier.position;oldPlacements=test.placements;after=EditorApplication.timeSinceStartup+.7;
                test.implanter.StartCycle();Check(!test.implanter.Running,"Ion start bypassed transport/HOLD gate");
                ScreenCapture.CaptureScreenshot("OHT_Animation_HOLD.png");SessionState.SetInt(Key,6);
            }
            else if(phase==6&&EditorApplication.timeSinceStartup>after)
            {
                Check(test.placements==oldPlacements&&Vector3.Distance(frozen,test.carrier.position)<.001f,"HOLD dispatched carrier");
                test.ellipsometer.demoHold=false;test.ellipsometer.StartScan();SessionState.SetInt(Key,7);
            }
            else if(phase==7&&test.ellipsometer.completed&&test.ellipsometer.verdict=="PASS")
            {
                Check(test.ellipsometer.lotHeld&&!test.ellipsometer.CanProceed,"PASS automatically released HOLD");
                Check(test.ellipsometer.ApproveRelease(),"Review release failed");SessionState.SetInt(Key,8);
            }
            else if(phase==8&&test.completed)
            {
                Check(test.completedRuns==2&&test.placements==4&&!test.failed,"Second sequence did not finish");
                Check(test.stocker.Stored&&test.stocker.outgoingRuns==2&&test.stocker.incomingRuns==2&&test.stocker.OccupiedCount==3&&!test.stocker.DoorOpen,"Second stocker return failed");
                File.WriteAllText("OhtFabPlay.result","OHT_FAB_PLAY_OK\nIndividual oxidation/metrology/implant starts and full cycles work while OHT is idle; OHT refuses takeover while equipment is busy; individual starts restored after completion.\nTwo full storage slot -> stocker I/O -> oxide -> ellipsometer -> implant -> I/O -> reserved storage slot loops; pause; 2mm grip/dock checks; raised travel; wafer return and closed doors before pickup; HOLD blocks transport and implant and keeps return slot reserved; PASS remeasurement requires review release.\nProcess values are simulation/demo data; no TCAD/Jetson connection added.");
                Time.timeScale=1;SessionState.SetInt(Key,9);EditorApplication.isPlaying=false;return;
            }
            else if(phase==9&&!EditorApplication.isPlayingOrWillChangePlaymode)
            {SessionState.SetInt(Key,0);return;}
            if((phase>1&&phase<9||phase==10||phase==11)&&(test.failed||EditorApplication.timeSinceStartup>deadline))throw new Exception("OHT failed/timed out: "+test.status);
        }
        catch(Exception e)
        {File.WriteAllText("OhtFabPlay.result",e.ToString());Debug.LogException(e);Time.timeScale=1;SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;}
    }
}
#endif
