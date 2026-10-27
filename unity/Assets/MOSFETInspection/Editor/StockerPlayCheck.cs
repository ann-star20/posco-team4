#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class StockerPlayCheck
{
    const string Key="Stocker.PlayPhase";
    static StockerCycle stocker;
    static double after,deadline;
    static Vector3 frozen;
    static StockerPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("StockerPlay.once")||EditorApplication.isPlaying||EditorApplication.isPlayingOrWillChangePlaymode)return;
                try{File.Delete("StockerPlay.once");}catch(IOException){return;}
                SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                stocker=UnityEngine.Object.FindAnyObjectByType<StockerCycle>();
                Check(stocker&&!stocker.Running&&stocker.Stored&&!stocker.failed,"Stocker must start stored and idle");
                Check(stocker.occupied.Length==6&&stocker.OccupiedCount==3,"Initial six-slot inventory incorrect");
                Check(Vector3.Distance(stocker.oht.foupDock.position,stocker.slots[0].position)<.002f,"FOUP not initially in slot 1");
                Check(stocker.oht.oxidation.TransportAvailable&&stocker.oht.ellipsometer.TransportAvailable&&stocker.oht.implanter.TransportAvailable,"Stocker locked individual equipment");
                Application.runInBackground=true;Time.timeScale=8;FactoryControlBar.Select(FactoryControlBar.Equipment.Stocker);
                stocker.ToggleInside();stocker.View();stocker.StartDispatch();deadline=EditorApplication.timeSinceStartup+120;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&stocker.location==StockerCycle.CarrierLocation.Fork&&stocker.status=="EXTRACT FROM SLOT")
            {
                stocker.TogglePause();frozen=stocker.oht.foup.position;after=EditorApplication.timeSinceStartup+.6;
                ScreenCapture.CaptureScreenshot("Stocker_Animation_Extract.png");SessionState.SetInt(Key,3);
            }
            else if(phase==3&&EditorApplication.timeSinceStartup>after)
            {
                Check(Vector3.Distance(frozen,stocker.oht.foup.position)<.001f,"Paused stocker payload moved");
                stocker.oht.StartCycle();Check(!stocker.oht.Running,"OHT interrupted stocker dispatch");
                stocker.TogglePause();SessionState.SetInt(Key,4);
            }
            else if(phase==4&&stocker.AtPort&&!stocker.Running)
            {
                Check(stocker.outgoingRuns==1&&!stocker.occupied[0]&&stocker.reservedSlot==0,"Dispatch did not reserve empty return slot");
                Check(!stocker.DoorOpen&&Vector3.Distance(stocker.oht.foupDock.position,stocker.ioDock.position)<.002f,"Dispatch docking/door failed");
                ScreenCapture.CaptureScreenshot("Stocker_Animation_AtPort.png");after=EditorApplication.timeSinceStartup+.6;SessionState.SetInt(Key,5);
            }
            else if(phase==5&&EditorApplication.timeSinceStartup>after){stocker.StartReceive();SessionState.SetInt(Key,6);}
            else if(phase==6&&stocker.Stored&&!stocker.Running)
            {
                Check(stocker.incomingRuns==1&&stocker.occupied[0]&&stocker.OccupiedCount==3,"Stocker inventory not restored");
                Check(!stocker.DoorOpen&&Vector3.Distance(stocker.oht.foupDock.position,stocker.slots[0].position)<.002f,"FOUP not returned to reserved slot");
                ScreenCapture.CaptureScreenshot("Stocker_Animation_Stored.png");
                File.WriteAllText("StockerPlay.result","STOCKER_PLAY_OK\nSlot 1 -> fork -> I/O -> reserved slot 1; six-slot inventory preserved; pause; OHT takeover blocked during stocker motion; shutter interlock; 2mm dock checks; fork/payload versus cabinet, shelves and stored carrier envelope checks throughout motion.\nSimplified demonstration mechanism; not vendor motion certification.");
                Time.timeScale=1;SessionState.SetInt(Key,7);EditorApplication.isPlaying=false;return;
            }
            else if(phase==7&&!EditorApplication.isPlaying&&!EditorApplication.isPlayingOrWillChangePlaymode){SessionState.SetInt(Key,0);return;}
            if(phase>=2&&phase<=6&&(stocker.failed||EditorApplication.timeSinceStartup>deadline))throw new Exception("Stocker failed/timed out: "+stocker.status);
        }
        catch(Exception e){File.WriteAllText("StockerPlay.result",e.ToString());Debug.LogException(e);Time.timeScale=1;SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;}
    }
}
#endif
