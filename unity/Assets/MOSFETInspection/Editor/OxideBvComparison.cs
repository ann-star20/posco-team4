#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

// A paired experiment: identical synthetic oxide anomaly, wafer count, and model; only BV availability differs.
[InitializeOnLoad]
public static class OxideBvComparison
{
    const string Key="OXIDE_BV_COMPARISON_PHASE";
    const string Folder="Tools/JetsonML/BVComparison";
    static ProcessAnalysisView view;
    static LotProcessAnalysis.Scenario scenario;
    static ProcessAnalysisView.Payload[] results;
    static int index;
    static string lastRequest,runId;
    static float dose,target;
    static bool held,canSort;
    static double deadline;
    [Serializable] class Report
    {
        public string status,scenario_id,baseline_version,ground_truth="산화막",data_source="synthetic",execution="Jetson fresh GP+TabPFN requests",limitation="GP-generated synthetic electrical data; not independent TCAD validation or physical measurements";
        public float dose_ratio=1,epi_ratio=1,oxide_ratio,bv_value;
        public int n_wafers;
        public bool only_bv_availability_changed,tcad_executed=false,recipe_applied=false;
        public ProcessAnalysisView.Payload without_bv,with_bv;
    }
    static OxideBvComparison(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static bool Same(float a,float b)=>a==b;
    // JsonUtility stores missing nullable BV as zero internally; exported records must preserve absence as null.
    static string Export(object value)=>System.Text.RegularExpressions.Regex.Replace(JsonUtility.ToJson(value,true),"(\"bv\"\\s*:\\s*)0(?:\\.0)?(?=\\s*[,}])","${1}null");
    static string Verdict(ProcessAnalysisView.Payload p)=>!p.decided?"구분 불가":p.top_cause=="산화막"?"주입 원인과 일치":"주입 원인과 불일치";
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("OxideBvComparison.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("OxideBvComparison.once");SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase>=2&&!Application.isPlaying){SessionState.SetInt(Key,0);return;}
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                Directory.CreateDirectory(Folder);view=ProcessAnalysisView.Instance;
                Check(view&&LotProcessAnalysis.Instance,"Analysis components unavailable");
                scenario=LotProcessAnalysis.Instance.PairedScenario;
                Check(scenario!=null&&scenario.measurement!=null&&Mathf.Abs(scenario.oxide_ratio-1.09f)<.00001f,"Expected current +9% oxide scenario");
                Check(scenario.measurement.bv>0&&scenario.n_wafers==5,"Same-scenario BV/wafer data missing");
                var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();var socket=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();
                dose=ion.targetDose;target=film.recipe.targetNm;held=film.lotHeld;canSort=socket.feed.CanSort;
                index=0;results=new ProcessAnalysisView.Payload[2];runId=Guid.NewGuid().ToString("N").Substring(0,10);
                File.WriteAllText(Folder+"/status.txt","Waiting for existing Jetson diagnostic worker. Only BV availability will differ.");
                deadline=EditorApplication.timeSinceStartup+90;SessionState.SetInt(Key,2);
            }
            else if(phase==2)
            {
                if(view.CanRequest)
                {
                    var input=ProcessAnalysisView.NewInput("BV-COMPARE-OX09-"+runId,scenario.baseline_version,scenario.n_wafers,scenario.measurement);
                    lastRequest=input.request_id;
                    File.AppendAllText(Folder+"/status.txt","\nREQUEST "+(index==0?"without_bv":"with_bv")+" "+lastRequest);
                    _=view.RequestInput(input,index==1);deadline=EditorApplication.timeSinceStartup+220;SessionState.SetInt(Key,3);
                }
                else Check(EditorApplication.timeSinceStartup<deadline,"Jetson worker did not become ready");
            }
            else if(phase==3)
            {
                if(view.LastCompletedRequest==lastRequest)
                {
                    var p=view.Current;
                    Check(p!=null&&p.request_id==lastRequest&&p.input!=null&&p.delivery=="computed","Uncorrelated or replayed result");
                    Check(p.mode=="gp_tabpfn","High precision was not used: "+p.warning);
                    Check(p.input.n_wafers==scenario.n_wafers&&!p.applied&&p.tcad_status=="not_run","Unexpected wafer count/application/TCAD state");
                    Check(Same(p.input.measurement.vth,scenario.measurement.vth)&&Same(p.input.measurement.gm,scenario.measurement.gm)&&Same(p.input.measurement.id4v,scenario.measurement.id4v),"Electrical values changed");
                    Check(index==0?p.input.measurement.bv==0:Same(p.input.measurement.bv,scenario.measurement.bv),"Incorrect BV availability/value");
                    results[index]=p;File.WriteAllText(Folder+"/"+(index==0?"without-bv":"with-bv")+".json",Export(p));
                    File.AppendAllText(Folder+"/status.txt",$"\nRESULT {p.top_cause} {p.top_probability:P4} {p.decision} {p.duration_seconds:F2}s");
                    index++;deadline=EditorApplication.timeSinceStartup+30;SessionState.SetInt(Key,index==2?4:2);
                }
                else
                {
                    Check(view.RequestPending,"Analysis request failed: "+view.RequestState+" "+view.LastError);
                    Check(EditorApplication.timeSinceStartup<deadline,"Comparison request timed out");
                }
            }
            else if(phase==4)
            {
                var a=results[0];var b=results[1];
                Check(a.lot_id==b.lot_id&&a.request_id!=b.request_id&&a.baseline_version==b.baseline_version&&a.model_version==b.model_version,"Comparison LOT/model identity changed");
                Check(Same(a.input.measurement.vth,b.input.measurement.vth)&&Same(a.input.measurement.gm,b.input.measurement.gm)&&Same(a.input.measurement.id4v,b.input.measurement.id4v)&&a.input.n_wafers==b.input.n_wafers,"More than BV changed");
                var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();var socket=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();
                Check(film.lotHeld==held&&film.recipe.targetNm==target&&ion.targetDose==dose&&socket.feed.CanSort==canSort,"Comparison changed process or AOI state");
                var report=new Report{status="completed",scenario_id=scenario.scenario_id,baseline_version=scenario.baseline_version,oxide_ratio=scenario.oxide_ratio,bv_value=scenario.measurement.bv,n_wafers=scenario.n_wafers,only_bv_availability_changed=true,without_bv=a,with_bv=b};
                File.WriteAllText(Folder+"/result.json",Export(report));
                string md=$"# 동일 산화막 이상: BV 정보 유무 비교\n\n실제 Jetson에서 요청마다 새 GP+TabPFN 계산. 합성 전기특성, 실제 계측/독립 TCAD 검증 아님.\n\n- 시나리오: {scenario.scenario_id}\n- 주입 조건: 도즈 1 / 에피 1 / 산화막 {scenario.oxide_ratio:F2}\n- 웨이퍼 수: 양쪽 모두 {scenario.n_wafers}장 가정\n- Vth {scenario.measurement.vth:R} V / gm {scenario.measurement.gm:R} A/V/um / Id {scenario.measurement.id4v:R} A/um — 동일\n- 추가 정보: BV {scenario.measurement.bv:F6} V\n\n| 입력 | 최다 후보 | 후보 확률 | 판정 | 주입 원인 대조 | 계산 시간 |\n|---|---|---:|---|---|---:|\n| BV 없음 | {a.top_cause} | {100*a.top_probability:F2}% | {a.decision} | {Verdict(a)} | {a.duration_seconds:F2}s |\n| BV 있음 | {b.top_cause} | {100*b.top_probability:F2}% | {b.decision} | {Verdict(b)} | {b.duration_seconds:F2}s |\n\n판정 기준 70%와 모델은 변경하지 않았다. 서로 다른 최다 후보의 확률 차이를 동일 원인의 확률 상승으로 해석하면 안 된다. 보정안은 실제 TCAD 미검증이며 승인·적용하지 않았다. 이 단일 합성 비교는 일반 진단 정확도를 보장하지 않는다.\n";
                File.WriteAllText(Folder+"/comparison.md",md);File.AppendAllText(Folder+"/status.txt","\nOXIDE_BV_JETSON_COMPARISON_COMPLETE");
                SessionState.SetInt(Key,0);
            }
        }
        catch(Exception e)
        {
            Directory.CreateDirectory(Folder);File.WriteAllText(Folder+"/failure.txt",e.ToString());File.AppendAllText(Folder+"/status.txt","\nFAILED: "+e.Message);
            SessionState.SetInt(Key,0);UnityEngine.Debug.LogException(e);
        }
    }
}
#endif
