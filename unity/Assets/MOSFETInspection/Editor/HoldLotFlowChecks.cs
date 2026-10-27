#if UNITY_EDITOR
using System;
using System.Collections;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad] public static class HoldLotFlowChecks
{
    const string Key="HoldLotFlow.phase";
    static HoldLotFlowChecks(){EditorApplication.update+=Tick;}
    static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
    static void Drain(IEnumerator task)
    {
        int steps=0;
        try{while(task.MoveNext()){Check(++steps<20000,"Animation did not finish");if(task.Current is IEnumerator child)Drain(child);}}
        finally{(task as IDisposable)?.Dispose();}
    }
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        if(phase==2)
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode)return;
            EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"enabled",false);
            EditorSettings.enterPlayModeOptions=(EnterPlayModeOptions)SessionState.GetInt(Key+"flags",0);SessionState.SetInt(Key,0);return;
        }
        if(phase==0)
        {
            if(!(File.Exists("HoldLotFlowCheck.once")||File.Exists("NormalLotExportCheck.once")||File.Exists("OhtCsvReadinessCheck.once")||File.Exists("ManualLotRemoveCheck.once")||File.Exists("FilmResultDisplayCheck.once"))||EditorApplication.isPlayingOrWillChangePlaymode)return;
            File.Delete("HoldLotFlowCheck.once");File.Delete("NormalLotExportCheck.once");File.Delete("OhtCsvReadinessCheck.once");File.Delete("ManualLotRemoveCheck.once");File.Delete("FilmResultDisplayCheck.once");
            SessionState.SetBool(Key+"enabled",EditorSettings.enterPlayModeOptionsEnabled);SessionState.SetInt(Key+"flags",(int)EditorSettings.enterPlayModeOptions);
            EditorSettings.enterPlayModeOptionsEnabled=false;SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
        }
        if(!Application.isPlaying)return;
        try{Run();File.WriteAllText("FilmResultDisplayCheck.result","FILM_RESULT_DISPLAY_AND_FLOW_OK\n"+DateTime.UtcNow.ToString("O")+"\nReal scene geometry + film and implantation wafer-return animations + OHT travel/pick/place + stocker collision checks / two NG held FOUPs preserved / normal film and ion physically dispatched and slots freed / next LOT both equipment / old TCAD late response stays on old inspection / finite full capacity / manual X removal of parked and active NG carriers preserves requests/history / busy and stale-row deletion rejected / no network requests");}
        catch(Exception error){File.WriteAllText("FilmResultDisplayCheck.result","FAILED: "+error);Debug.LogException(error);}
        finally{SessionState.SetInt(Key,2);EditorApplication.isPlaying=false;}
    }
    static void Set(object target,string name,object value)=>target.GetType().GetField(name,BindingFlags.NonPublic|BindingFlags.Instance).SetValue(target,value);
    static void Recover(OhtFabCycle o,int port)
    {Drain((IEnumerator)typeof(OhtFabCycle).GetMethod("RecoverStandalone",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(o,new object[]{port}));}
    static void Export(OhtFabCycle o,OhtFabCycle.HeldLot item)
    {Drain((IEnumerator)typeof(OhtFabCycle).GetMethod("ExportNormal",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(o,new object[]{item}));}
    static JetsonTestDataProtocol.Selection Selection(JetsonTestDataProtocol.Dataset d,string id)=>new JetsonTestDataProtocol.Selection{
        row=Array.Find(d.rows,r=>r.id==id).Snapshot(),measurement_source="TCAD",dataset_sha256=d.dataset_sha256,n_wafers=1,reference_target_nm=60};
    static void Run()
    {
        HoldLotIsolationChecks.Run();
        var o=UnityEngine.Object.FindAnyObjectByType<OhtFabCycle>();Check(o&&o.stocker,"Missing OHT scene");
        var f=o.ellipsometer;var ion=o.implanter;var s=o.stocker;var bridge=GatewayInspectionBridge.Instance;
        var manager=LotProcessAnalysis.Instance;var view=ProcessAnalysisView.Instance;
        Check(bridge&&manager&&view,"Missing inspection services");
        bridge.Disarm();bridge.enabled=false;bridge.EnsureSession();bridge.Token="offline-hold-fixture";Check(bridge.Arm(),"Offline capture arm failed");
        manager.enabled=false;view.enabled=false;
        var legacy=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();if(legacy)legacy.enabled=false;
        o.enabled=false;ion.enabled=false;o.validationDelta=s.validationDelta=f.validationDelta=ion.validationDelta=.1f;
        var csv=UnityEngine.Object.FindAnyObjectByType<JetsonTestDataView>();var data=JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(File.ReadAllText("Temp/ion-dataset-offline.json"));
        Set(csv,"dataset",null);
        Check(!JetsonTestDataView.CanPrepareOht(f,ion,out var missing)&&missing.Contains("CSV"),"Missing ion data allowed OHT departure");
        o.StartCycle();Check(!o.Running&&!o.failed&&o.status.Contains("START WAIT"),"Missing CSV locked OHT as a fatal fault");
        csv.UseTestDataset(data);
        Check(JetsonTestDataView.CanPrepareOht(f,ion,out var restored),"Loaded dataset cannot recover readiness: "+restored);
        Set(csv,"automatic",false);
        var filmStore=FilmInspectionHistory.Instance;var ionStore=IonImplantHistory.Instance;
        FilmInspectionHistory.UseTestStore(new FilmInspectionHistory("Temp/HoldIsolation/film.json"));IonImplantHistory.UseTestStore(new IonImplantHistory("Temp/HoldIsolation/ion.json"));
        try
        {
            f.lotId="LOT-001";f.waferId="OFFLINE-HOLD-FILM";f.transportControlled=false;f.SetCsvTest(Selection(data,"B081"));
            Drain(f.Cycle());Check(f.SafeToUnload&&o.NeedsQuarantine(2),"Film did not finish safely with HOLD");
            Check(f.DisplayResultText.Contains(f.Mean.ToString("F1"))&&f.DisplayResultText.Contains(f.verdict)&&f.DisplayResultText.Contains(f.InspectionId.Substring(0,8)),"Completed film display missing actual values/inspection identity");
            string filmId=f.InspectionId;var first=bridge.FullCycleJob(filmId);Check(first!=null,"Film job missing");
            first.cycle.Accept(GatewayFullCycleChecks.Prediction(first.cycle,3.27,3.89,2.47,50.44).ToString());first.cycle.DiagnosisJson();
            first.cycle.Accept(GatewayFullCycleChecks.Diagnosis(first.cycle,"tcad_verify").ToString());
            Check(first.cycle.WaitingTcad,"Old TCAD not waiting");string frozen=GatewayInspectionBridge.RequestJson(first);
            Recover(o,2);Check(o.IsParked(filmId)&&s.IsHeldSlot(0)&&s.Stored&&!o.Running,"Film not stored or OHT still blocked");
            Check(f.lotHeld&&!f.CanProceed,"HOLD illegally released");
            Check(o.PrepareNextLot(2),"Next film LOT blocked by old TCAD: "+o.HoldNotice);
            string next=f.lotId;Check(next!="LOT-001"&&s.reservedSlot==1&&s.IsHeldSlot(0),"Held FOUP overwritten or LOT reused");
            Check(s.slots[0].Find("HOLD_FOUP_"+filmId),"Parked FOUP visual disappeared");
            f.ResetPreview();
            Check(f.DisplayResultText.Contains("이전 검사")&&f.DisplayResultText.Contains("LOT-001")&&f.DisplayResultText.Contains(filmId.Substring(0,8)),"Next LOT reset erased previous completed result");
            Check(!f.completed&&f.verdict=="PENDING"&&float.IsNaN(f.Mean)&&!f.CanProceed,"Previous display result released a new unmeasured LOT");
            f.SetCsvTest(Selection(data,"B001"));Drain(f.Cycle());
            Check(f.DisplayResultText.Contains(f.InspectionId.Substring(0,8))&&!f.DisplayResultText.Contains(filmId.Substring(0,8)),"New result did not replace previous display");
            var normal=bridge.FullCycleJob(f.InspectionId);Check(normal!=null&&normal.request.lot_id==next,"New film request missing");
            normal.cycle.Accept(GatewayFullCycleChecks.Prediction(normal.cycle,2.2,4,5,45).ToString());
            Check(normal.cycle.Done&&f.CanProceed&&!o.NeedsQuarantine(2),"New normal film blocked by old TCAD");
            Check(first.cycle.WaitingTcad&&GatewayInspectionBridge.RequestJson(first)==frozen,"Old request changed/cancelled by next film");
            ion.transportControlled=false;ion.useJetsonCsv=true;ion.SetCsvTest(Selection(data,"B081"));Drain(ion.Cycle());
            string ionId=ion.InspectionId;var second=bridge.FullCycleJob(ionId);Check(second!=null&&ion.SafeToUnload&&o.NeedsQuarantine(3),"Ion HOLD missing");
            Recover(o,3);Check(ion.status.Contains("보관 완료")&&!ion.status.Contains("회수 후"),"Recovery panel kept waiting message after storage");Check(s.IsHeldSlot(0)&&s.IsHeldSlot(1)&&o.HeldLots.Count==2,"Ion overwrote film HOLD");
            Check(o.PrepareNextLot(3),"New ion blocked by old TCAD");
            Check(ion.incomingLotId!=next&&s.reservedSlot==2&&s.CanDispatchReserved,"Next ion carrier not separate");
            ion.SetCsvTest(Selection(data,"B001"));Drain(ion.Cycle());
            Check(bridge.FullCycleJob(ion.InspectionId)!=null&&ion.incomingLotId!=second.request.lot_id,"Next ion failed independent capture");
            var normalIon=bridge.FullCycleJob(ion.InspectionId);
            Check(!normalIon.cycle.NormalInspection,"Pending ion mistakenly normal");
            // Normal original data can arrive after the physical carrier was parked.
            Recover(o,3);Check(o.HeldLots.Count==3&&s.IsHeldSlot(2),"Pending ion not parked");
            normalIon.cycle.Accept(GatewayFullCycleChecks.Prediction(normalIon.cycle,2.2,4,5,45).ToString());
            Check(normalIon.cycle.NormalInspection,"Both-OK result not eligible for export");
            Export(o,o.HeldLots[2]);
            Check(o.HeldLots.Count==2&&!s.occupied[2]&&!s.IsHeldSlot(2)&&s.Exported,"Normal ion slot not freed");
            Check(o.PrepareNextLot(2),"Next LOT cannot reuse normally exported carrier slot");
            f.SetCsvTest(Selection(data,"B001"));Drain(f.Cycle());
            var normalFilm=bridge.FullCycleJob(f.InspectionId);Recover(o,2);
            Check(o.PrepareNextLot(3),"Cannot prepare next input while film prediction waits");
            int activeSlot=s.reservedSlot;var activeFoup=o.foup;
            Check(s.NextFreeSlot==-1,"Full-capacity export fixture not full");
            normalFilm.cycle.Accept(GatewayFullCycleChecks.Prediction(normalFilm.cycle,2.2,4,5,45).ToString());
            Check(normalFilm.cycle.NormalInspection,"Normal film result missing");
            int freed=o.HeldLots[2].slot;Export(o,o.HeldLots[2]);
            Check(s.reservedSlot==activeSlot&&o.foup==activeFoup&&s.Stored&&s.occupied[activeSlot],"Exported another carrier corrupted active input");
            Check(!s.occupied[freed]&&!s.IsHeldSlot(freed)&&o.HeldLots.Count==2,"Normal film slot not freed");
            Check(s.IsHeldSlot(0)&&s.IsHeldSlot(1)&&first.cycle.WaitingTcad,"Normal export cleared an NG HOLD");
            bool rejected=false;try{Drain(s.ExportNormal(0,filmId));}catch(InvalidOperationException){rejected=true;}
            Check(rejected&&s.IsHeldSlot(0),"Stocker allowed NG export without normal proof");
            var late=new Unity.Plastic.Newtonsoft.Json.Linq.JObject{["sequence"]=3,["event_id"]=Guid.NewGuid().ToString(),["run_id"]=first.cycle.Run,
                ["event_type"]="tcad.verification.batch_completed",["payload"]=new Unity.Plastic.Newtonsoft.Json.Linq.JObject{
                    ["request_id"]=first.cycle.DiagnosisId,["job_id"]=first.cycle.DiagnosisJob,["proposal_id"]=Guid.NewGuid().ToString()}};
            first.cycle.Accept(late.ToString());
            Check(!first.cycle.NormalInspection&&!o.CanAutoExport(o.HeldLots[0]),"TCAD completion released NG");
            Check(first.cycle.Done&&normal.cycle.Done&&o.HeldLots.Count==2&&s.IsHeldSlot(0)&&s.IsHeldSlot(1),"Late TCAD released/overwrote another LOT");
            Check(manager.ForInspection(filmId)?.lotId=="LOT-001"&&manager.ForInspection(normal.inspectionId)?.lotId==next,"Old record lost");
            Check(first.cycle.Sequence>normal.cycle.Sequence&&GatewayInspectionBridge.RequestJson(first)==frozen,"Late result attached to wrong job");
            Check(o.PrepareNextLot(2),"Cannot bind ready input after another carrier export");
            f.SetCsvTest(Selection(data,"B001"));Drain(f.Cycle());
            var alreadyNormal=bridge.FullCycleJob(f.InspectionId);alreadyNormal.cycle.Accept(GatewayFullCycleChecks.Prediction(alreadyNormal.cycle,2.2,4,5,45).ToString());
            Recover(o,2);Check(o.CanAutoExport(o.HeldLots[2]),"Normal received before unload not exportable");
            Export(o,o.HeldLots[2]);Check(o.HeldLots.Count==2&&s.Exported,"Already-normal film was left in stocker");
            var removed=o.HeldLots[0];string oldRequest=GatewayInspectionBridge.RequestJson(first);
            Set(o,"running",true);Check(!o.ManualRemove(removed)&&s.IsHeldSlot(0),"Manual delete during OHT movement");Set(o,"running",false);
            Check(o.ManualRemove(removed)&&removed.manualRemoved&&removed.qualityHold&&removed.exported,"NG manual removal changed quality verdict");
            Check(!s.occupied[0]&&!s.IsHeldSlot(0)&&s.IsHeldSlot(1)&&o.HeldLots.Count==1,"Manual delete cleared wrong slots");
            Check(first.cycle.Done&&GatewayInspectionBridge.RequestJson(first)==oldRequest&&manager.ForInspection(filmId).electricalVerdict==ElectricalSpec.Verdict.NG,"Manual delete modified request/diagnosis/inspection history");
            Check(o.PrepareNextLot(3),"No next inspection after manual deletion");
            Check(s.reservedSlot==0&&s.occupied[0],"Freed slot not reused");
            Check(!o.ManualRemove(removed)&&s.occupied[0],"Old X button removed a replacement LOT");
            ion.SetCsvTest(Selection(data,"B081"));Drain(ion.Cycle());Recover(o,3);
            var activeRemoved=o.HeldLots[1];Check(activeRemoved.slot==s.reservedSlot&&o.ManualRemove(activeRemoved),"Cannot delete current reserved HOLD carrier");
            Check(s.Exported&&!s.occupied[activeRemoved.slot]&&o.HeldLots.Count==1,"Current carrier slot not released");
            Check(o.PrepareNextLot(3)&&s.occupied[s.reservedSlot],"Cannot seed new LOT after current carrier removal");
        }
        finally
        {
            FilmInspectionHistory.UseTestStore(filmStore);IonImplantHistory.UseTestStore(ionStore);
            foreach(var j in bridge.Jobs)foreach(var suffix in new[]{".json",".inspection.json",".events.jsonl"})if(j.request?.request_id!=null)File.Delete("Tools/Gateway/Requests/"+j.request.request_id+suffix);
            File.Delete("Tools/Logistics/Hold/session-"+o.GetEntityId().ToString().Replace(':','-')+".json");
        }
    }
}
#endif
