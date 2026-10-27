#if UNITY_EDITOR
using System;
using System.Collections;
using System.IO;
using UnityEditor;
using UnityEngine;
using Unity.Plastic.Newtonsoft.Json.Linq;

[InitializeOnLoad]
public static class IonJetsonCsvChecks
{
    const string Key="ION_JETSON_CSV_CHECK";
    static double started,after;
    static IonJetsonCsvChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string reason){if(!ok)throw new Exception(reason);}
    static void RunCycle(IEnumerator step)
    {
        int steps=0;
        try{while(step.MoveNext()){Check(++steps<10000,"Cycle did not terminate");if(step.Current is IEnumerator child)RunCycle(child);}}
        finally{(step as IDisposable)?.Dispose();}
    }
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(SessionState.GetInt(Key,0)==2)
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode)return;
            EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"OptionsEnabled",false);
            EditorSettings.enterPlayModeOptions=(EnterPlayModeOptions)SessionState.GetInt(Key+"Options",0);
            SessionState.SetInt(Key,0);return;
        }
        try
        {
            if(SessionState.GetInt(Key,0)==3)
            {
                if(EditorApplication.timeSinceStartup<after)return;
                ScreenCapture.CaptureScreenshot("Temp/IonGateway/IonAnalyzerWindow.png");after=EditorApplication.timeSinceStartup+10;SessionState.SetInt(Key,4);return;
            }
            if(SessionState.GetInt(Key,0)==4)
            {
                if(!File.Exists("Temp/IonGateway/IonAnalyzerWindow.png")){Check(EditorApplication.timeSinceStartup<after,"Analyzer screenshot not produced");return;}
                File.AppendAllText("IonJetsonCsvCheck.result","\nTCAD analyzer opened automatically / exact inspection and CSV / 4 electrical rows / micro units / electrical verdict / screenshot: Temp/IonGateway/IonAnalyzerWindow.png");
                SessionState.SetInt(Key,2);EditorApplication.isPlaying=false;return;
            }
            if(SessionState.GetInt(Key,0)==0)
            {
                if(!File.Exists("IonNormalWireCheck.once")||EditorApplication.isPlayingOrWillChangePlaymode)return;
                File.Delete("IonNormalWireCheck.once");
                SessionState.SetBool(Key+"OptionsEnabled",EditorSettings.enterPlayModeOptionsEnabled);
                SessionState.SetInt(Key+"Options",(int)EditorSettings.enterPlayModeOptions);
                EditorSettings.enterPlayModeOptionsEnabled=false;
                SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(!Application.isPlaying)return;
            var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();var csv=UnityEngine.Object.FindAnyObjectByType<JetsonTestDataView>();
            if(!ion||!csv){if(started==0)started=EditorApplication.timeSinceStartup;Check(EditorApplication.timeSinceStartup-started<45,"Scene components missing");return;}
            var bridge=GatewayInspectionBridge.Instance;if(bridge)bridge.Disarm();
            Check(bridge,"Gateway bridge missing");bridge.enabled=false;bridge.EnsureSession();
            bridge.Token="offline-test-not-a-real-token";Check(bridge.Arm(),"Offline capture could not arm");
            var legacy=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();if(legacy)legacy.enabled=false;
            var analysis=LotProcessAnalysis.Instance;if(analysis)analysis.enabled=false;
            ion.enabled=false;ion.transportControlled=false;ion.lotQualityGate=null;ion.validationDelta=.05f;
            ion.incomingLotId="LOT-001";ion.incomingWaferId="OFFLINE-CSV-ION-TEST";ion.useJetsonCsv=true;
            var data=JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(File.ReadAllText("Temp/ion-dataset-offline.json"));
            var original=IonImplantHistory.Instance;
            IonImplantHistory.UseTestStore(new IonImplantHistory("Temp/IonCsvCheck/"+Guid.NewGuid().ToString("N")+".json"));
            try
            {
                csv.UseTestDataset(data);string first=null;
                for(int i=0;i<3;i++)
                {
                    if(i>0){Check(JetsonTestDataView.TryIonInput(ion,out var next,true)&&ion.SetCsvTest(next),"New ion wafer not prepared");}
                    Check(JetsonTestDataView.TryIonInput(ion,out var prepared),"CSV preparation failed: "+typeof(JetsonTestDataView).GetField("status",System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Instance).GetValue(csv));
                    RunCycle(ion.Cycle());Check(ion.completed&&!ion.failed,"CSV cycle not completed: "+ion.status);
                    var selection=ion.InspectionCsv;
                    Check(selection!=null&&selection.category==new[]{"normal","dose","electrical"}[i],"Ion sample sequence incorrect");
                    double expected=JetsonTestDataProtocol.Dose(7.7e12,selection.row);
                    Check(Math.Abs(ion.dose-expected)/expected<1e-6,"Dose does not match frozen Jetson CSV ratio");
                    Check(ion.dashboard.DoseVerdict==(i==1?"FAIL":"OK"),"Dose verdict mismatch");
                    var captured=bridge.IonJob(ion.InspectionId);
                    Check(captured!=null&&captured.kind=="gateway_full_cycle"&&captured.cycle!=null&&captured.jobId==null,"Completion lost Gateway full cycle context");
                    Check(captured.state=="검사값 Gateway 전송 대기 · 예측 → 진단 → 조건부 TCAD","Full cycle not queued");
                    Check(bridge.Jobs.Count==i+(i>0?2:1),"Duplicate full-cycle jobs created");
                    var measurements=captured.normalRequest.input_payload.provenance.inspection_result.measurements;
                    Check(measurements.vth==selection.row.tcad.vth&&measurements.bv==selection.row.tcad.bv,"Another CSV row used in diagnosis");
                    Check(Math.Abs(measurements.gm-selection.row.tcad.gm*1e6)<1e-9&&Math.Abs(measurements.id_on-selection.row.tcad.id4v*1e6)<1e-9,"CSV micro conversion changed");
                    Check(ion.dashboard.disposition.text.Contains("TCAD CSV "+selection.row.id)&&ion.dashboard.disposition.text.Contains("전기특성 "+ElectricalSpec.Evaluate(selection.row.tcad.vth,selection.row.tcad.bv)),"Dashboard did not display TCAD electrical verdict without server response: "+ion.dashboard.disposition.text);
                    Check(GatewayInspectionBridge.RequestJson(captured).Contains("process_parameters"),"First step lost completed process values");
                    var analyzer=ProcessAnalysisView.Instance;
                    Check(analyzer&&analyzer.WindowOpen&&analyzer.AnalysisTab==0&&analyzer.IonInspectionId==ion.InspectionId,"Completed ion inspection did not open the TCAD analyzer electrical tab");
                    var table=analyzer.IonElectricalRows();
                    Check(table.Length==4&&table[0][1].Contains(selection.row.tcad.vth.ToString("F3"))&&table[2][1].Contains(measurements.gm.ToString("F3")),"Analyzer electrical table is blank or wrong units");
                    Check(analyzer.IonElectricalVerdict==ElectricalSpec.Evaluate(selection.row.tcad.vth,selection.row.tcad.bv),"Analyzer electrical verdict mismatch");
                    var flags=System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic;
                    var records=(System.Collections.IList)typeof(ProcessAnalysisView).GetField("ionInspections",flags).GetValue(analyzer);
                    var record=records[records.Count-1];
                    var directInput=(ProcessAnalysisView.Input)record.GetType().GetField("directInput").GetValue(record);
                    if(i==0)
                    {
                        Check(directInput==null&&!(bool)captured.GetType().GetField("finished",flags).GetValue(captured)&&(bool)captured.GetType().GetField("ready",flags).GetValue(captured)&&analyzer.IonDirectSummary(ion.InspectionId).Contains("보정 불필요"),"Normal record not queued or direct diagnosis started");
                        var normal=captured.normalRequest.input_payload.provenance.inspection_result;
                        Check(captured.diagnosisRequest==null&&captured.directDiagnosis==null&&captured.normalRequest!=null&&
                            captured.request.stage_id=="ion_inspection_record"&&normal.verdict=="OK"&&normal.dose_verdict=="OK"&&normal.electrical_verdict=="OK"&&
                            !normal.diagnosis_requested&&!normal.correction_candidate&&normal.dose_cm2==ion.dose,"Normal inspection lost verdict/dose or includes a correction");
                        Check(File.Exists("Tools/Gateway/Requests/"+captured.request.request_id+".json"),"Normal record not persisted for sending");
                        var export=JObject.Parse(GatewayInspectionBridge.RequestJson(captured));
                        Check(export["input_payload"]?["provenance"]?["tcad"]==null&&!export.ToString().Contains("diagnosis.requested"),"Normal wire contains a phantom candidate or diagnosis");
                        export["lot_id"]="LOT-UNITY-ION-NORMAL-TEST";
                        File.WriteAllText("Temp/IonGateway/ion-normal-live.request.json",export.ToString());
                    }
                    else Check(directInput==null&&!(bool)captured.GetType().GetField("finished",flags).GetValue(captured)&&(bool)captured.GetType().GetField("ready",flags).GetValue(captured),"NG did not prepare Gateway full cycle, or direct diagnosis duplicated");
                    if(i>0)
                    {
                        captured.cycle.Accept(GatewayFullCycleChecks.Prediction(captured.cycle,measurements.vth,measurements.gm,measurements.id_on,measurements.bv).ToString());
                        Check(captured.cycle.PendingDiagnosis,"Either NG skipped Gateway diagnosis");
                        var body=JObject.Parse(captured.cycle.DiagnosisJson());
                        Check((double)body["input_payload"]["measurements"]["gm"]==measurements.gm&&(string)body["run_id"]==captured.request.run_id,"Diagnosis unit/RUN changed");
                        var eventBody=GatewayFullCycleChecks.Diagnosis(captured.cycle,"tcad_verify");
                        Check(captured.cycle.Accept(eventBody.ToString())&&captured.cycle.WaitingTcad,"Gateway diagnosis/TCAD route lost");
                        Check(!captured.cycle.Accept(eventBody.ToString())&&bridge.Jobs.Count==(i+2),"Duplicate diagnosis created extra jobs");
                        Check(captured.directDiagnosis==null&&captured.diagnosisRequest==null,"Direct worker diagnosis still present");
                        analyzer.SetAnalysisTab(0);
                    }
                    var refValues=ion.InspectionCondition;
                    var snapshot=new IonGatewayProtocol.Snapshot{inspection_id=ion.InspectionId,lot_id=ion.incomingLotId,unit_id=ion.InspectionUnitId,
                        dose_cm2=ion.dose,epi_doping=refValues.epi_doping*selection.row.epi_doping_ratio,oxide_thickness_um=refValues.oxide_reference_um*selection.row.oxide_ratio,
                        csv_sample_id=selection.row.id,csv_sha256=selection.dataset_sha256};
                    var request=IonGatewayProtocol.Build(snapshot);
                    Check(request.input_payload.process_parameters.body_dose==ion.dose,"Dose multiplied by CSV twice");
                    Check(request.input_payload.provenance.sample_id==selection.row.id&&request.input_payload.provenance.data_source=="jetson_csv_test","Gateway sample provenance lost");
                    if(i==0){first=selection.row.id;RunCycle(ion.Cycle());Check(ion.InspectionCsv.row.id==first,"Retest changed wafer values");}
                }
                Check(bridge.Jobs.Count==4&&System.Linq.Enumerable.All(bridge.Jobs,j=>j.ion!=null&&j.cycle!=null&&j.jobId==null),"Unexpected duplicate full-cycle jobs or network acknowledgements");
                csv.UseTestDataset(new JetsonTestDataProtocol.Dataset{schema_version=1,data_source="jetson_csv_test",dataset_sha256=new string('a',64),epi_semantics="drift_doping_ratio",rows=new[]{data.rows[0]}});
                Check(!JetsonTestDataView.TryIonInput(ion,out _,true),"Incomplete CSV generated invented case");
                File.WriteAllText("IonJetsonCsvCheck.result","ION_JETSON_CSV_PLAY_OK\nFull cycles: original CSV record preserved / dose exact / prediction -> Gateway diagnosis -> conditional TCAD / micro units unchanged / direct worker suppressed / same inspection and RUN / duplicate blocked / frozen retest / missing categories blocked\nBridge network update disabled; no server requests sent. Offline fixtures only");
            }
            finally
            {
                IonImplantHistory.UseTestStore(original);bridge.Disarm();
                foreach(var j in bridge.Jobs)
                    foreach(var suffix in new[]{".json",".inspection.json"})
                        File.Delete(Path.Combine("Tools/Gateway/Requests",j.request.request_id+suffix));
            }
            File.Delete("Temp/IonGateway/IonAnalyzerWindow.png");
            EditorApplication.ExecuteMenuItem("Window/General/Game");after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,3);
        }
        catch(Exception e){File.WriteAllText("IonJetsonCsvCheck.result","FAILED: "+e);SessionState.SetInt(Key,2);EditorApplication.isPlaying=false;Debug.LogException(e);}
    }
}
#endif
