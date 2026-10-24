#if UNITY_EDITOR
using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.Media;
using UnityEditor.SceneManagement;
using UnityEngine;
using Unity.Plastic.Newtonsoft.Json.Linq;

[InitializeOnLoad] public static class DemoMovieRecorder
{
    const string Phase="FactoryDemoMoviePhase";
    static bool cleaned;
    public static bool IsRecordingSession=>SessionState.GetInt(Phase,0)==2;
    public const string Output="Tools/VideoDemo/2026-10-24";
    static DemoMovieRecorder(){EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Phase,0);
        if(phase==0&&!cleaned){
            foreach(var capture in Resources.FindObjectsOfTypeAll<DemoMovieCapture>().Where(c=>c&&c.gameObject.scene.IsValid()))
                UnityEngine.Object.DestroyImmediate(capture.gameObject.name=="Temporary demo recorder"?(UnityEngine.Object)capture.gameObject:capture);
            cleaned=true;
        }
        if(phase==0&&(File.Exists("DemoMovieProbe.once")||File.Exists("DemoMovieFull.once"))){
            if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
            bool full=File.Exists("DemoMovieFull.once");File.Delete(full?"DemoMovieFull.once":"DemoMovieProbe.once");SessionState.SetBool(Phase+"Full",full);Directory.CreateDirectory(Output);
            var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();EditorSceneManager.SaveScene(scene);
            File.Copy(scene.path,Output+"/BeforeRecording.unity",true);
            SessionState.SetBool(Phase+"Options",EditorSettings.enterPlayModeOptionsEnabled);EditorSettings.enterPlayModeOptionsEnabled=false;
            cleaned=false;SessionState.SetInt(Phase,1);EditorApplication.isPlaying=true;return;
        }
        if(phase==1&&Application.isPlaying){
            var gameType=typeof(Editor).Assembly.GetType("UnityEditor.GameView");var game=Resources.FindObjectsOfTypeAll(gameType).Cast<EditorWindow>().First();
            var size=gameType.GetProperty("selectedSizeIndex",BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic);
            SessionState.SetInt(Phase+"Size",(int)size.GetValue(game));size.SetValue(game,3);game.Show();game.Focus();
            var go=new GameObject("Temporary demo recorder"){hideFlags=HideFlags.DontSave};go.AddComponent<DemoMovieCapture>().full=SessionState.GetBool(Phase+"Full",false);SessionState.SetInt(Phase,2);
        }
        if(phase==3&&!EditorApplication.isPlayingOrWillChangePlaymode){
            EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Phase+"Options",false);
            var gameType=typeof(Editor).Assembly.GetType("UnityEditor.GameView");var game=Resources.FindObjectsOfTypeAll(gameType).FirstOrDefault();
            if(game!=null)gameType.GetProperty("selectedSizeIndex",BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic).SetValue(game,SessionState.GetInt(Phase+"Size",7));
            SessionState.SetInt(Phase,0);
        }
    }
    public static void Done(){SessionState.SetInt(Phase,3);EditorApplication.isPlaying=false;}
}

public class DemoMovieCapture:MonoBehaviour
{
    public bool full;
    MediaEncoder encoder;Font font;string caption="MOSFET 공정·검사 디지털 트윈",badge="Unity 실제 Game 화면 녹화 · 공정 시뮬레이션";
    OhtFabCycle o;AoiJetsonFeed aoi;ProcessAnalysisView analysis;GatewayTcadApprovalView approval;
    GatewayInspectionBridge.Job replayJob;
    Camera[] cameras;bool oxInside,filmInside,ionInside,filmWindow,ionWindow,aoiWindow,ngFilmStarted,nextLotStarted;
    int shot=-1,frames;float movieTime;
    string lastCaption;float captionStart;int subtitleCount;
    float oxidationCompletedAt=-1;bool omitIdleFrame;
    readonly string root=DemoMovieRecorder.Output;
    static readonly BindingFlags Private=BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public;
    [Serializable]class Replay{public string request_json,proposal_json;public string[] events;}
    class Subtitle{public float start,end;public string text;}
    Subtitle[] subs;
    void Cam(Camera camera){if(!camera)return;foreach(var c in cameras)if(c&&!c.targetTexture)c.enabled=c==camera;}
    static void Field(object owner,string name,object value){owner.GetType().GetField(name,Private).SetValue(owner,value);}
    void CloseAnalysis(){if(analysis)typeof(ProcessAnalysisView).GetProperty("WindowOpen").SetValue(analysis,false);}
    void SetupFull(){
        o=FindAnyObjectByType<OhtFabCycle>();if(!o||o.Running||o.failed)throw new Exception("OHT not ready for recording");
        analysis=ProcessAnalysisView.Instance;if(LotProcessAnalysis.Instance)LotProcessAnalysis.Instance.enabled=false;
        FilmInspectionHistory.UseTestStore(new FilmInspectionHistory(root+"/CapturedFilmHistory.json"));
        IonImplantHistory.UseTestStore(new IonImplantHistory(root+"/CapturedIonHistory.json"));
        AoiInspectionHistory.UseTestStore(new AoiInspectionHistory(root+"/CapturedAoiHistory.json"));
        var csv=FindAnyObjectByType<JetsonTestDataView>();csv.UseTestDataset(JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(File.ReadAllText("Temp/ion-dataset-offline.json")));csv.enabled=false;
        foreach(var bar in FindObjectsByType<FactoryControlBar>(FindObjectsInactive.Include))bar.enabled=false;
        cameras=FindObjectsByType<Camera>(FindObjectsInactive.Include);aoi=FindAnyObjectByType<AoiJetsonFeed>();aoi.useWebSocket=false;
        o.lot_id="LOT-001";o.ellipsometer.lotId=o.implanter.incomingLotId=o.lot_id;o.ellipsometer.lotHeld=false;
        GatewayLotConditions.ForLot(o.lot_id);
        FactoryControlBar.Select(FactoryControlBar.Equipment.Overview);Cam(o.overview);o.overview.fieldOfView=42;
        // Subtitles follow the edited 280-second recording, not wall-clock encoding time.
        subs=System.Text.RegularExpressions.Regex.Split(File.ReadAllText(root+"/MOSFET_시연자막_4분40초.srt").Trim(),@"\r?\n\r?\n").Select(block=>{
            var lines=block.TrimStart('\uFEFF').Split('\n');var times=lines[1].Trim().Split(new[]{" --> "},StringSplitOptions.None);
            float Seconds(string t)=>(float)TimeSpan.Parse(t.Replace(',','.')).TotalSeconds;
            return new Subtitle{start=Seconds(times[0]),end=Seconds(times[1]),text=string.Join("\n",lines.Skip(2)).Trim()};
        }).ToArray();
        ReplayResults();CloseAnalysis();
        File.WriteAllText(root+"/RecordingPreflight.result","RECORDING_PREFLIGHT_OK\nLOT-001 reference condition resolved. Original Gateway prediction, diagnosis and both REAL TCAD results replayed and validated before recording.\n");
    }
    void Need(bool ok,string why){if(!ok)throw new Exception(why+" / "+o.status);}
    void SaveCaption(float end){
        if(string.IsNullOrEmpty(lastCaption)||end<=captionStart)return;
        string Stamp(float seconds)=>TimeSpan.FromSeconds(seconds).ToString(@"hh\:mm\:ss\,fff");
        File.AppendAllText(root+"/MOSFET_Demo_실제녹화.srt",(++subtitleCount)+"\n"+Stamp(captionStart)+" --> "+Stamp(end)+"\n"+lastCaption+"\n\n",System.Text.Encoding.UTF8);
    }
    void TrackCaption(){if(lastCaption==caption)return;SaveCaption(frames/15f);lastCaption=caption;captionStart=frames/15f;}
    void StartFilm(bool ng){o.ellipsometer.demoHold=ng;o.ellipsometer.StartScan();Need(o.Running,"Film dispatch did not start");}
    void ReplayResults(){
        var data=JsonUtility.FromJson<Replay>(File.ReadAllText(root+"/RecordedGatewayReplay.json"));var request=JsonUtility.FromJson<GatewayInspectionProtocol.Request>(data.request_json);
        var original=JObject.Parse(data.request_json);var provenance=original["input_payload"]?["provenance"];var result=provenance?["inspection_result"];
        string physical=(string)(result?["thickness_verdict"]??result?["dose_verdict"]),electrical=(string)result?["electrical_verdict"];
        replayJob=new GatewayInspectionBridge.Job{request=request,inspectionId=(string)provenance?["inspection_id"],kind="gateway_full_cycle",state="기존 Gateway 수신 기록 재생 · 신규 전송 없음"};
        replayJob.cycle=new GatewayFullCycleProtocol.State(request.run_id,request.request_id,request.lot_id,request.unit_id,physical=="OK",electrical=="OK",electrical=="OK"||electrical=="NG");
        foreach(var raw in data.events){var e=JObject.Parse(raw);string type=(string)e["event_type"];
            if(type=="diagnosis.completed"){replayJob.cycle.DiagnosisJson();typeof(GatewayFullCycleProtocol.State).GetProperty("DiagnosisId").SetValue(replayJob.cycle,(string)e["payload"]["request_id"]);}
            if(type=="tcad.verification.review_required"){replayJob.cycle.ObserveReview((string)e["payload"]["proposal_id"]);replayJob.cycle.ObserveReviewEvent(raw);}else replayJob.cycle.Accept(raw);
            replayJob.rawEvent=raw;
        }
        Need(replayJob.cycle.Candidates.Count==2&&replayJob.cycle.ReviewRequired,"Recorded REAL TCAD events could not be replayed");
        analysis.OpenFullCycle(replayJob);analysis.SetAnalysisTab(1);
        Field(analysis,"window",new Rect(95,8,1090,688));
    }
    void ShowApproval(){
        CloseAnalysis();var data=JsonUtility.FromJson<Replay>(File.ReadAllText(root+"/RecordedGatewayReplay.json"));
        approval=GatewayTcadApprovalView.For(GatewayInspectionBridge.Instance);
        var reviewType=typeof(GatewayTcadApprovalView).GetNestedType("Review",BindingFlags.NonPublic);var review=Activator.CreateInstance(reviewType);
        Field(review,"job",replayJob);Field(review,"proposal",JsonUtility.FromJson<GatewayTcadApprovalProtocol.Proposal>(data.proposal_json));Field(review,"selected",0);
        Field(approval,"active",review);Field(approval,"open",true);Field(approval,"busy",false);Field(approval,"actor","시연 관리자");Field(approval,"status","기존 REAL TCAD 기록 · 승인창 시연 / 요청 전송 없음");
    }
    void Shot(int s){
        if(shot==s)return;shot=s;File.AppendAllText(root+"/CaptureEvents.log",$"{movieTime:F3}s | shot {s} | {o.status}\n");
        if(s==1){Time.timeScale=4;o.oxidation.StartCycle();Need(o.Running,"Oxidation dispatch did not start");FactoryControlBar.Select(FactoryControlBar.Equipment.Overview);}
        if(s==2){Need(o.completed&&!o.Running&&o.SingleDockedPort==1,"Oxidation did not finish within shot");if(oxInside){o.oxidation.ShowInside();oxInside=false;}StartFilm(false);Time.timeScale=4;}
        if(s==3){Need(o.completed&&!o.Running&&o.ellipsometer.CanProceed,"Normal film inspection incomplete");o.ellipsometer.dashboard.SetSignalMonitorOpen(false);filmWindow=false;CloseAnalysis();if(filmInside){o.ellipsometer.ShowInside();filmInside=false;}o.implanter.StartCycle();Need(o.Running,"Ion dispatch did not start");Time.timeScale=9;}
        if(s==4){Need(o.completed&&!o.Running,"Ion inspection incomplete");if(ionWindow){o.implanter.dashboard.ToggleWindow();ionWindow=false;}if(ionInside){o.implanter.ShowInside();ionInside=false;}CloseAnalysis();Time.timeScale=1;FactoryControlBar.Select(FactoryControlBar.Equipment.AOI);Cam(aoi.sorter.overview);aoi.SetMode(true);aoi.Demo("crash");aoi.dashboard.ToggleWindow();aoiWindow=true;}
        if(s==5){if(aoiWindow){aoi.dashboard.ToggleWindow();aoiWindow=false;}FactoryControlBar.Select(FactoryControlBar.Equipment.Overview);o.lot_id="SIM-LOT-DEMO-NG-002";GatewayLotConditions.RegisterSimulationLot(o.lot_id,GatewayLotConditions.ForLot("LOT-001"));Time.timeScale=14;o.oxidation.StartCycle();Need(o.Running,"NG demonstration could not start");Cam(o.overview);}
        if(s==6){Time.timeScale=0;ReplayResults();FactoryControlBar.Select(FactoryControlBar.Equipment.Overview);Cam(o.overview);}
        if(s==7)analysis.SetAnalysisTab(2);
        if(s==8)analysis.SetAnalysisTab(3);
        if(s==9)ShowApproval();
        if(s==10){var r=typeof(GatewayTcadApprovalView).GetField("active",Private).GetValue(approval);typeof(GatewayTcadApprovalView).GetMethod("BeginAdmin",Private).Invoke(approval,new[]{r,(object)true});}
        if(s==11){if(approval)approval.enabled=false;CloseAnalysis();FactoryControlBar.Select(FactoryControlBar.Equipment.Overview);Cam(o.overview);}
    }
    void FullFrame(){
        omitIdleFrame=false;
        var sub=subs.FirstOrDefault(s=>movieTime>=s.start&&movieTime<s.end);caption=sub?.text??"";
        badge=movieTime<175?"Unity 실제 화면 · CSV/공정 시뮬레이션 · 서버 신규 전송 없음":movieTime<205?"HOLD 격리·후속 LOT 동작 시연 · 시험 데이터":movieTime<245?"Gateway 기존 수신 기록 재생 · 신규 진단/승인 요청 없음":movieTime<265?"기존 REAL TCAD 결과 · 승인창 시연 · 승인 전송 없음":"MOSFET 공정·검사 디지털 트윈";
        if(movieTime<20){Shot(0);Cam(o.overview);Time.timeScale=0;}
        else if(movieTime<80){Shot(1);
            if(o.oxidation.Running){
                Time.timeScale=1.4f;if(!oxInside){o.oxidation.ShowInside();oxInside=true;}Cam(o.oxidation.detail);
                string state=o.oxidation.status;
                caption=state.Contains("OPEN")?"FOUP와 투입구 문을 열어 웨이퍼를 준비합니다.":state.Contains("PICK")?"로봇이 FOUP에서 웨이퍼를 꺼냅니다.":state.Contains("TRANSFER")||state.Contains("ON BOAT")?"웨이퍼를 산화로 보트로 이송합니다.":state.Contains("BOAT UP")?"보트를 올려 웨이퍼를 공정관에 투입합니다.":state.Contains("SIMULATED")?"산화 공정의 내부 동작을 시뮬레이션합니다.":state.Contains("BOAT DOWN")?"공정을 마친 보트를 아래로 내립니다.":state.Contains("RETURN")?"로봇이 웨이퍼를 회수해 FOUP로 돌려보냅니다.":state.Contains("CLOSE")?"웨이퍼 복귀 후 FOUP와 투입구 문을 닫습니다.":"산화로 내부 웨이퍼 이송 동작";
            }else if(o.completed){Time.timeScale=0;Cam(o.oxidation.detail);caption="산화 공정 완료 · 웨이퍼가 FOUP로 복귀했습니다.";if(oxidationCompletedAt<0)oxidationCompletedAt=movieTime;omitIdleFrame=movieTime-oxidationCompletedAt>7&&movieTime<79.9f;}else{Time.timeScale=4;Cam(o.followCamera);caption="스토커에서 출고한 FOUP를 OHT로 산화로에 이송합니다.";}
        }
        else if(movieTime<120){Shot(2);
            if(o.ellipsometer.Running){Time.timeScale=2.5f;if(!filmInside){o.ellipsometer.ShowInside();filmInside=true;}Cam(o.ellipsometer.detail);caption="앨립소미터에서 웨이퍼를 이송하고\n3개 지점의 산화막 두께를 측정합니다.";}
            else if(o.completed){Time.timeScale=0;Cam(o.ellipsometer.detail);if(!filmWindow){o.ellipsometer.dashboard.SetSignalMonitorOpen(true);filmWindow=true;}if(movieTime>=109){o.ellipsometer.dashboard.SetSignalMonitorOpen(false);analysis.OpenLot(o.ellipsometer.lotId);analysis.SetAnalysisTab(0);}}
            else{Cam(o.followCamera);caption="산화로에서 FOUP를 인수해 앨립소미터로 이송합니다.";}
        }
        else if(movieTime<155){Shot(3);
            if(o.implanter.Running){if(!ionInside){o.implanter.ShowInside();ionInside=true;}Cam(o.implanter.internalView);caption="이온주입기 내부의 웨이퍼 이송·진공·주입 동작을 재현합니다.";}
            else if(o.completed){Time.timeScale=0;Cam(o.implanter.detail);if(!ionWindow){o.implanter.dashboard.ToggleWindow();ionWindow=true;}}
            else{Cam(o.followCamera);caption="앨립소미터에서 이온주입기로 FOUP를 이송합니다.";}
        }
        else if(movieTime<175){Shot(4);if(movieTime>168&&aoi.CanSort&&!aoi.sorter.Running)aoi.BeginSort();}
        else if(movieTime<205){Shot(5);
            CloseAnalysis();
            caption=!ngFilmStarted?"NG 사례를 재현하고 HOLD 격리 이송을 확인합니다.":!nextLotStarted?"NG LOT를 HOLD로 분리해 스토커로 회수합니다.":"HOLD LOT를 보관하면서 다음 LOT의 공정을 시작합니다.";
            if(!ngFilmStarted&&o.completed&&!o.Running&&o.SingleDockedPort==1){StartFilm(true);ngFilmStarted=true;}
            if(ngFilmStarted&&o.ellipsometer.Running&&movieTime<192)Cam(o.ellipsometer.detail);
            else if(ngFilmStarted&&o.Running&&!o.oxidation.Running&&!nextLotStarted)Cam(o.followCamera);
            else Cam(o.overview);
            if(ngFilmStarted&&o.completed&&!o.Running&&o.ellipsometer.lotHeld&&!nextLotStarted){
                File.AppendAllText(root+"/CaptureEvents.log",$"{movieTime:F3}s | NG isolated: {o.ellipsometer.InspectionId} | held lots={o.HeldLots.Count}\n");
                o.lot_id="SIM-LOT-DEMO-NEXT-003";GatewayLotConditions.RegisterSimulationLot(o.lot_id,GatewayLotConditions.ForLot("LOT-001"));o.oxidation.StartCycle();Need(o.Running,"Next LOT blocked after quarantine");nextLotStarted=true;
            }
        }
        else if(movieTime<222)Shot(6);
        else if(movieTime<240)Shot(7);
        else if(movieTime<252)Shot(8);
        else if(movieTime<259)Shot(9);
        else if(movieTime<265)Shot(10);
        else Shot(11);
        if(movieTime>=205)Need(nextLotStarted,"HOLD quarantine/next LOT continuation was not demonstrated");
        if(!omitIdleFrame)TrackCaption();
        Need(!o.failed&&!o.stocker.failed&&!o.oxidation.failed&&!o.ellipsometer.failed&&!o.implanter.failed,"Equipment failed during recording");
    }
    void OnGUI(){
        if(encoder==null||!DemoMovieRecorder.IsRecordingSession)return;
        int depth=GUI.depth;
        var matrix=GUI.matrix;GUI.matrix=Matrix4x4.identity;GUI.depth=-10000;
        if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Arial"},32);
        var style=new GUIStyle(GUI.skin.label){font=font,fontSize=Mathf.RoundToInt(Screen.height/27f),alignment=TextAnchor.MiddleCenter,wordWrap=true};style.normal.textColor=Color.white;
        var old=GUI.color;GUI.color=new Color(.025f,.04f,.065f,.92f);GUI.DrawTexture(new Rect(Screen.width*.08f,Screen.height*.84f,Screen.width*.84f,Screen.height*.13f),Texture2D.whiteTexture);GUI.color=old;
        GUI.Label(new Rect(Screen.width*.1f,Screen.height*.845f,Screen.width*.80f,Screen.height*.12f),caption,style);
        style.fontSize=Mathf.RoundToInt(Screen.height/50f);style.alignment=TextAnchor.MiddleLeft;
        GUI.color=new Color(.025f,.04f,.065f,.88f);GUI.DrawTexture(new Rect(20,18,Screen.width*.64f,46),Texture2D.whiteTexture);GUI.color=old;GUI.Label(new Rect(32,20,Screen.width*.62f,42),badge,style);GUI.matrix=matrix;GUI.depth=depth;
    }
    IEnumerator Start(){
        if(!DemoMovieRecorder.IsRecordingSession){Destroy(this);yield break;}
        var bridge=GatewayInspectionBridge.Instance;if(bridge){bridge.Disarm();bridge.enabled=false;}
        foreach(var socket in FindObjectsByType<AoiWebSocketClient>(FindObjectsInactive.Include))socket.enabled=false;
        Application.runInBackground=true;Time.captureFramerate=15;Time.timeScale=1;
        for(int i=0;i<20;i++)yield return null;
        try{
            if(full)SetupFull();
            encoder=new MediaEncoder(Path.GetFullPath(root+(full?"/MOSFET_Demo_4m40s.mp4":"/RecordingProbe.mp4")),new VideoTrackAttributes{frameRate=new MediaRational(15),width=(uint)Screen.width,height=(uint)Screen.height,includeAlpha=false});
        }catch(Exception e){File.WriteAllText(root+(full?"/RecordingFull.result":"/RecordingProbe.result"),"FAILED PREFLIGHT\n"+e);DemoMovieRecorder.Done();yield break;}
        int total=full?4200:30;
        for(int i=0;i<total;i++){
            movieTime=i/15f;
            if(full){try{FullFrame();}catch(Exception e){File.WriteAllText(root+"/RecordingFull.result","FAILED at "+movieTime+"\n"+e);encoder.Dispose();encoder=null;Time.timeScale=1;DemoMovieRecorder.Done();yield break;}}
            if(full&&omitIdleFrame){yield return null;continue;}
            yield return new WaitForEndOfFrame();var frame=ScreenCapture.CaptureScreenshotAsTexture();
            try{
                if(!full&&i==15)File.WriteAllBytes(root+"/RecordingProbe.png",frame.EncodeToPNG());
                if(full&&i%150==0){File.WriteAllBytes(root+"/Frame-"+frames.ToString("D5")+".png",frame.EncodeToPNG());File.WriteAllText(root+"/RecordingFull.progress",$"{frames} encoded frames | source {movieTime:F1}/280s | shot={shot} | {o.status}");}
                encoder.AddFrame(frame);frames++;
            }finally{Destroy(frame);}
        }
        encoder.Dispose();encoder=null;if(full)SaveCaption(frames/15f);Time.captureFramerate=0;Time.timeScale=1;File.WriteAllText(root+(full?"/RecordingFull.result":"/RecordingProbe.result"),"UNITY_GAME_RECORDING_OK\n"+Screen.width+"x"+Screen.height+" / 15 fps / "+frames+" frames / "+(frames/15f)+" seconds / Korean captions baked in\n"+DateTime.UtcNow.ToString("O")+"\nActual Unity Game screen captured. Offline CSV/process/AOI demonstration; original Gateway/REAL TCAD event replay; approval modal display only. No control requests, approval, recipe application. Saved scene unchanged.");DemoMovieRecorder.Done();
    }
    void OnDestroy(){encoder?.Dispose();encoder=null;Time.captureFramerate=0;}
}
#endif
