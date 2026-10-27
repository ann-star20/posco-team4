#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad] public static class SingleToolOhtCheck
{
    const string Key="SingleToolOhtCheckPhase";
    static OhtFabCycle o;static double deadline,after;static bool processed,carried;static int phasePort,round;static string lot,wafer;
    static SingleToolOhtCheck(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0),port=SessionState.GetInt(Key+"Port",1);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("SingleToolOht.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("SingleToolOht.once");var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();Check(EditorSceneManager.SaveScene(scene),"Scene save failed");
                SessionState.SetString(Key+"Scene",scene.path);SessionState.SetBool(Key+"Options",EditorSettings.enterPlayModeOptionsEnabled);
                EditorSettings.enterPlayModeOptionsEnabled=false;SessionState.SetInt(Key+"Port",1);SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                o=UnityEngine.Object.FindAnyObjectByType<OhtFabCycle>();Check(o&&!o.failed&&!o.Running,"OHT must start idle");
                var bridge=GatewayInspectionBridge.Instance;if(bridge){bridge.Disarm();bridge.enabled=false;}
                if(LotProcessAnalysis.Instance)LotProcessAnalysis.Instance.enabled=false;
                var legacy=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();if(legacy)legacy.enabled=false;
                FilmInspectionHistory.UseTestStore(new FilmInspectionHistory("Temp/SingleToolOht/film-"+port+".json"));
                IonImplantHistory.UseTestStore(new IonImplantHistory("Temp/SingleToolOht/ion-"+port+".json"));
                var csv=UnityEngine.Object.FindAnyObjectByType<JetsonTestDataView>();Check(csv,"CSV panel missing");
                csv.UseTestDataset(JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(File.ReadAllText("Temp/ion-dataset-offline.json")));
                o.lot_id="LOT-001";o.ellipsometer.lotId=o.implanter.incomingLotId="LOT-001";o.ellipsometer.lotHeld=false;
                Application.runInBackground=true;Time.timeScale=10;round=0;
                o.ellipsometer.StartScan();Check(!o.Running,"Ellipsometer dispatched from stocker without upstream FOUP");
                o.implanter.StartCycle();Check(!o.Running,"Ion dispatched without ellipsometer FOUP");
                StartPort(1);return;
            }
            if(phase==2)
            {
                Check(o&&phasePort==port,"Runtime check context lost");
                Check(!o.failed&&!o.stocker.failed&&!o.oxidation.failed&&!o.ellipsometer.failed&&!o.implanter.failed,"Equipment/transport failure: "+o.status);
                Check(EditorApplication.timeSinceStartup<deadline,"Single tool route timed out: "+port+" / "+o.status);
                if(port>=2&&!carried&&!o.Held)Check(o.command!="MOVE","Empty OHT drove a lap before picking up at its current stop");
                if(o.Held)carried=true;
                bool selected=port==1?o.oxidation.Running:port==2?o.ellipsometer.Running:o.implanter.Running;if(selected)processed=true;
                Check((port==1||!o.oxidation.Running)&&(port==2||!o.ellipsometer.Running)&&(port==3||!o.implanter.Running),"Unselected equipment ran");
                if(!o.completed||o.Running)return;
                Check(processed&&carried&&!o.Held,"Selected tool did not complete: "+port);
                Check(o.stocker.outgoingRuns==round+1,"Unexpected extra stocker dispatch");
                if(port<3&&!(round==1&&port==2))
                {
                    Check(o.placements==1&&o.SingleDockedPort==port&&o.stocker.location==StockerCycle.CarrierLocation.InTransit,"FOUP did not stay at completed tool");
                    Check(o.stationCarriers[port].gameObject.activeInHierarchy,"Completed source FOUP hidden");
                    if(port==1){lot=o.oxidation.lotId;Check(lot==o.lot_id,"Oxidation LOT mismatch");}
                    else{Check(o.ellipsometer.lotId==lot&&o.ellipsometer.CanProceed,"Normal film not ready for ion");wafer=o.ellipsometer.waferId;}
                    File.AppendAllText("SingleToolOht.progress","ROUND "+round+" PORT "+port+" OK: source="+(port-1)+", selected process only, FOUP retained at tool.\n");
                    after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,4);return;
                }
                Check(o.placements==2&&o.stocker.Stored&&o.stocker.incomingRuns==round+1,"Final/HOLD FOUP not received by stocker");
                if(round==0)
                {
                    Check(o.implanter.incomingLotId==lot&&o.implanter.InspectionUnitId==wafer,"LOT/wafer changed between film and ion");
                    Check(o.IsParked(o.implanter.InspectionId),"Final inspection association lost");
                    File.AppendAllText("SingleToolOht.progress","NORMAL CHAIN OK: stocker -> oxidation -> ellipsometer -> ion -> stocker; one dispatch, same LOT/wafer.\n");
                    round=1;StartPort(1);return;
                }
                Check(o.ellipsometer.lotHeld&&o.IsParked(o.ellipsometer.InspectionId)&&o.HeldLots.Count==2,"NG quarantine lost prior LOT/history");
                int completed=o.completedRuns;o.implanter.StartCycle();Check(!o.Running&&o.completedRuns==completed,"NG LOT forwarded to ion");
                File.AppendAllText("SingleToolOht.progress","NG CHAIN OK: oxidation -> NG film -> stocker quarantine; ion forwarding blocked; earlier inspection retained.\n");
                Time.timeScale=1;SessionState.SetInt(Key,3);EditorApplication.isPlaying=false;return;
            }
            if(phase==4&&EditorApplication.timeSinceStartup>after)
            {
                Check(o.SingleDockedPort==port&&o.stationCarriers[port].gameObject.activeInHierarchy,"Waiting FOUP auto-recovered or disappeared");
                StartPort(port+1);return;
            }
            if(phase==3&&!EditorApplication.isPlayingOrWillChangePlaymode)
            {
                EditorSceneManager.OpenScene(SessionState.GetString(Key+"Scene",""));
                EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"Options",false);SessionState.SetInt(Key,0);File.WriteAllText("SingleToolOht.result","SINGLE_TOOL_CHAIN_SOURCES_OK\n"+DateTime.UtcNow.ToString("O")+"\n"+File.ReadAllText("SingleToolOht.progress")+"Offline CSV fixture; Gateway disarmed; no server requests.\n");
            }
        }
        catch(Exception e)
        {
            Time.timeScale=1;File.WriteAllText("SingleToolOht.result","FAILED\n"+e);Debug.LogException(e);
            EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"Options",false);SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
        }
    }
    static void StartPort(int port)
    {
        processed=carried=false;phasePort=port;SessionState.SetInt(Key+"Port",port);
        if(port==1)o.oxidation.StartCycle();else if(port==2)o.ellipsometer.StartScan();else o.implanter.StartCycle();
        Check(o.Running&&!o.oxidation.Running&&!o.ellipsometer.Running&&!o.implanter.Running,"Inspection began before delivery, or wrong source blocked start: "+port+" / "+o.HoldNotice);
        Check(o.source_port==(port==1?"STOCKER_IO":port==2?"OX_LOADPORT":"ELLIP_LOADPORT"),"Wrong pickup source for selected tool");
        int runs=o.completedRuns;o.StartSingleTool(port==3?1:3);Check(o.completedRuns==runs&&o.Running,"Busy start replaced active route");
        deadline=EditorApplication.timeSinceStartup+120;SessionState.SetInt(Key,2);
    }
}
#endif
