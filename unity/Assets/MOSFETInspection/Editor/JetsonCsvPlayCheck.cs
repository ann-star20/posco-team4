#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

// Isolated, offline integration check. Only runs when its explicit marker exists.
[InitializeOnLoad]
public static class JetsonCsvPlayCheck
{
    const string Key="JETSON_CSV_AUTO_PLAY_CHECK";
    static double deadline;
    static JetsonCsvPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool condition,string reason){if(!condition)throw new Exception(reason);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        try
        {
            if(SessionState.GetInt(Key,0)==0)
            {
                if(!File.Exists("JetsonCsvAutoCheck.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("JetsonCsvAutoCheck.once");SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(!Application.isPlaying)return;
            var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();var manager=LotProcessAnalysis.Instance;
            if(!film||!manager){if(deadline==0)deadline=EditorApplication.timeSinceStartup+60;Check(EditorApplication.timeSinceStartup<deadline,"Missing film/analysis components");return;}
            manager.enabled=false;
            var socket=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();if(socket)socket.enabled=false;
            var path="Temp/JetsonCsvCheck/"+Guid.NewGuid().ToString("N")+".json";
            var store=new FilmInspectionHistory(path);FilmInspectionHistory.UseTestStore(store);
            var dataset=JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(File.ReadAllText("Temp/ElectricalVerdict/jetson-test-data.json"));JetsonTestDataProtocol.Validate(dataset);
            var normal=Array.Find(dataset.rows,r=>r.id=="B001");var high=Array.Find(dataset.rows,r=>r.id=="B038");var predicted=Array.Find(dataset.rows,r=>r.id=="N001");
            film.lotId="CSV-CHECK-NORMAL";film.ResetDashboardDemo();
            Check(film.SetCsvTest(new JetsonTestDataProtocol.Selection{row=normal,measurement_source="TCAD",dataset_sha256=dataset.dataset_sha256,n_wafers=1}),"CSV selection rejected");
            film.ResetPreview();film.readings=film.DemoReadings();film.EvaluateInspection();
            var record=manager.Latest(film.lotId);
            Check(film.verdict=="PASS"&&record.electricalVerdict==ElectricalSpec.Verdict.OK,"B001 did not pass thickness/electrical checks");
            Check(Mathf.Abs(record.electrical.measurement.vth-normal.tcad.vth)<1e-6f&&record.csv.row.id=="B001","TCAD quartet/provenance not bound to inspection");
            film.lotId="CSV-CHECK-HIGH";film.ResetDashboardDemo();
            Check(film.SetCsvTest(new JetsonTestDataProtocol.Selection{row=high,measurement_source="TCAD",dataset_sha256=dataset.dataset_sha256,n_wafers=1}),"High CSV selection rejected");
            film.ResetPreview();float expected=film.recipe.targetNm*high.oxide_ratio;
            film.SelectedCsv.row.oxide_ratio=1; // The current inspection must keep its own snapshot.
            film.readings=film.DemoReadings();film.EvaluateInspection();record=manager.Latest(film.lotId);
            Check(Mathf.Abs(film.Mean-expected)<.001f&&film.readings[0]==film.readings[1]&&film.readings[1]==film.readings[2],"CSV thickness snapshot/noise boundary failed");
            Check(film.verdict=="FAIL"&&film.lotHeld&&record.status==LotProcessAnalysis.Status.Queued&&record.electricalVerdict==ElectricalSpec.Verdict.NG,"CSV NG failed to HOLD and queue existing diagnosis");
            Check(!film.SetCsvTest(new JetsonTestDataProtocol.Selection{row=predicted,measurement_source="TCAD"}),"Missing TCAD silently accepted");
            var history=store.OnDay(DateTime.Today);Check(history.Count==2,"CSV history not saved");
            Check(history.Exists(e=>e.test_sample_id=="B038"&&e.measurement_source=="TCAD"&&e.dataset_sha256==dataset.dataset_sha256&&Mathf.Abs(e.test_epi_doping_ratio-high.epi_doping_ratio)<1e-6f),"History provenance/knobs missing");
            Check(manager.RequestsSent==0,"Offline test dispatched a Jetson diagnosis");
            var panel=UnityEngine.Object.FindAnyObjectByType<JetsonTestDataView>();Check(panel,"CSV panel missing");panel.UseTestDataset(dataset);
            film.lotId="CSV-AUTO-SEQUENCE";film.ResetDashboardDemo();
            Check(JetsonTestDataView.PrepareIncoming(film,true),"First automatic wafer not prepared");
            film.ResetPreview();film.readings=film.DemoReadings();film.EvaluateInspection();
            var first=film.InspectionCsv;Check(first.automatic&&first.category=="normal"&&film.verdict=="PASS","Automatic first case not normal");
            Check(JetsonTestDataView.PrepareIncoming(film),"Same wafer reinspection not prepared");film.ResetPreview();
            Check(film.InspectionCsv.wafer_key==first.wafer_key&&film.InspectionCsv.row.id==first.row.id,"Reinspection advanced CSV sequence");
            Check(JetsonTestDataView.PrepareIncoming(film,true),"Second automatic wafer not prepared");film.ResetPreview();film.readings=film.DemoReadings();film.EvaluateInspection();
            Check(film.InspectionCsv.category=="thickness"&&film.verdict=="FAIL"&&film.lotHeld,"Second automatic case not thickness HOLD");
            Check(JetsonTestDataView.PrepareIncoming(film,true),"Third automatic wafer not prepared");film.ResetPreview();film.readings=film.DemoReadings();film.EvaluateInspection();
            Check(film.InspectionCsv.category=="electrical"&&film.verdict=="PASS"&&manager.Latest(film.lotId).electricalVerdict==ElectricalSpec.Verdict.NG,"Third automatic case did not separate thickness and electrical verdicts");
            Check(film.lotHeld,"Automatic case change released existing HOLD");
            Check(store.OnDay(DateTime.Today).Exists(e=>e.test_selection_mode=="automatic"&&e.test_category=="electrical"&&!string.IsNullOrEmpty(e.test_wafer_key)),"Automatic history provenance missing");
            File.WriteAllText("JetsonCsvAutoCheck.result","JETSON_CSV_AUTO_PLAY_OK\nManual CSV cases; automatic normal -> thickness -> electrical; same wafer stable; HOLD retained; exact snapshot/no noise; missing TCAD blocked; history provenance retained; isolated offline check only.");
            SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
        }
        catch(Exception error){File.WriteAllText("JetsonCsvAutoCheck.result","FAILED: "+error);SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;Debug.LogException(error);}
    }
}
#endif
