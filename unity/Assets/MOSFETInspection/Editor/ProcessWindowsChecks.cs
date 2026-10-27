#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class ProcessWindowsChecks
{
    const string Phase="PROCESS_WINDOWS_CHECK_PHASE";
    [Serializable] class Fixture {public int version;public string type,source,target,message_id;public ProcessAnalysisView.Payload payload;}
    static double deadline,after;
    static ProcessAnalysisView view;
    static int tab;
    static ProcessWindowsChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Phase,0);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("ProcessWindowsCheck.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("ProcessWindowsCheck.once");SessionState.SetInt(Phase,1);deadline=EditorApplication.timeSinceStartup+60;EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                view=ProcessAnalysisView.Instance;if(!view){Check(EditorApplication.timeSinceStartup<deadline,"Analysis component did not load.");return;}
                var socket=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();if(socket)socket.enabled=false;
                var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();
                float dose=ion.targetDose,thickness=film.recipe.targetNm;bool held=film.lotHeld;
                Check(ProcessAnalysisView.PredictionTitle(null,false)=="전기특성 판정 대기","Missing input shown as OK.");
                Check(ProcessAnalysisView.PredictionTitle(new ProcessAnalysisView.Measurement{vth=2.2f,bv=0},false)=="전기특성 판정 대기","Missing BV shown as OK.");
                Check(ProcessAnalysisView.PredictionTitle(new ProcessAnalysisView.Measurement{vth=3.2f,bv=0},false)=="예측 전기특성 부적합","Out-of-range Vth hidden by absent BV.");
                var original=File.ReadAllText("Tools/FabSocket/process_analysis_fixture.json");
                for(int i=0;i<2;i++)
                {
                    var f=JsonUtility.FromJson<Fixture>(original);f.message_id="windows-ui-"+Guid.NewGuid().ToString("N");f.payload.proposal_id=f.message_id+"-proposal";f.payload.run_id=f.message_id+"-run";
                    f.payload.input=ProcessAnalysisView.NewInput(f.payload.lot_id,f.payload.baseline_version,100,new ProcessAnalysisView.Measurement{vth=i==0?2.2601f:3.2734f,gm=4.599e-6f,id4v=5.207e-6f,bv=i==0?41.115f:50.446f});
                    Check(view.Accept(JsonUtility.ToJson(f)),"Offline replay rejected.");
                    Check(ProcessAnalysisView.PredictionTitle(view.Current.input.measurement,true)==(i==0?"예측 전기특성 적합":"예측 전기특성 부적합"),"Prediction tied to cause score instead of electrical input.");
                }
                Check(view.History.Count>=2,"History not retained.");
                view.SelectResult(view.History.Count-2);Check(Mathf.Abs(view.Current.input.measurement.vth-2.2601f)<.00001f,"History selection lost input snapshot.");
                Check(ion.targetDose==dose&&film.recipe.targetNm==thickness&&film.lotHeld==held,"UI checks changed recipe or HOLD.");
                Check(!view.RequestPending,"UI checks started an analysis request.");
                view.Open();view.SetAnalysisTab(0);tab=0;after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Phase,2);return;
            }
            if(phase==2&&EditorApplication.timeSinceStartup>after)
            {
                Directory.CreateDirectory("Temp/ProcessWindows");ScreenCapture.CaptureScreenshot("Temp/ProcessWindows/Tab"+tab+".png");
                if(++tab<5){view.SetAnalysisTab(tab);Check(view.AnalysisTab==tab,"Tab switch failed.");after=EditorApplication.timeSinceStartup+.4;return;}
                view.SetAnalysisTab(0);File.WriteAllText("ProcessWindowsCheck.result","PROCESS_WINDOWS_PLAY_OK\nWindows UI / OK-NG-pending / missing BV / input-bound history / five tabs / readonly recipe and HOLD / offline replay only");
                SessionState.SetInt(Phase,0);EditorApplication.isPlaying=false;
            }
        }
        catch(Exception e){File.WriteAllText("ProcessWindowsCheck.result",e.ToString());Debug.LogException(e);SessionState.SetInt(Phase,0);EditorApplication.isPlaying=false;}
    }
}
#endif
