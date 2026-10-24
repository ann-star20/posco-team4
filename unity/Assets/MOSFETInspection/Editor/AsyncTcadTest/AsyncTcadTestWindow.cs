using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;
using Unity.Plastic.Newtonsoft.Json;
using Unity.Plastic.Newtonsoft.Json.Linq;

public sealed class AsyncTcadTestWindow : EditorWindow
{
    string origin="ws://192.168.213.12:8000", token="", lot="LOT-001", unit="MOSFET-001", input="";
    string status="요청 전 · 먼저 오프라인 검사를 실행하세요.", output="", evidence="";
    bool confirmed, attempted, busy;
    JObject request;
    AsyncTcadContract.State state;
    CancellationTokenSource lifetime;
    Vector2 scroll;

    [MenuItem("MOSFET/Gateway/TCAD 비동기 연동 테스트")]
    public static void Open() { GetWindow<AsyncTcadTestWindow>("TCAD 연동 테스트"); }
    void OnDisable() { lifetime?.Cancel(); token=""; }
    void OnGUI()
    {
        EditorGUILayout.HelpBox("독립 테스트 창입니다. 기존 설비 검사 연동은 변경하지 않습니다. 요청이 접수되면 Gateway가 실제 TCAD 작업을 자동 생성할 수 있습니다.",MessageType.Info);
        using (new EditorGUI.DisabledScope(busy || attempted))
        {
            origin=EditorGUILayout.TextField("Gateway",origin);
            token=EditorGUILayout.PasswordField("Gateway 요청 토큰",token);
            lot=EditorGUILayout.TextField("LOT",lot); unit=EditorGUILayout.TextField("UNIT",unit);
            if (GUILayout.Button("팀원 확인 예시 불러오기 (통신 시험값 · 실제 검사값 아님)"))
            {
                input=File.ReadAllText("Tools/Gateway/AsyncTcadTest/diagnosis-input.example.json"); confirmed=true;
            }
            if (GUILayout.Button("확인된 diagnosis input_payload JSON 불러오기"))
            {
                string path=EditorUtility.OpenFilePanel("diagnosis 입력 객체만 선택", "", "json");
                if (!string.IsNullOrEmpty(path)) input=File.ReadAllText(path);
            }
            input=EditorGUILayout.TextArea(input,GUILayout.Height(90));
            EditorGUILayout.LabelField("단위: Vth/BV V · gm µS/µm · id_on µA/µm · n_wafers=평균한 실제 장수");
            confirmed=EditorGUILayout.ToggleLeft("팀원에게 확인한 진단 입력 형식입니다 (surrogate 공정 입력과 다름)",confirmed);
            if (GUILayout.Button("1. 새 진단 요청 JSON 만들기 (전송 없음)"))
            {
                try
                {
                    if (!confirmed) throw new FormatException("진단 입력의 출처·평균한 웨이퍼 장수·µ 단위를 확인하세요.");
                    request=AsyncTcadContract.Build(input,Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),lot,unit);
                    evidence=Path.GetFullPath("Tools/Gateway/AsyncTcadTest/Runs/"+(string)request["request_id"]);
                    Directory.CreateDirectory(evidence);
                    File.WriteAllText(Path.Combine(evidence,"request.json"),request.ToString(Formatting.Indented));
                    output=request.ToString(Formatting.Indented); status="요청 생성 완료 · 아직 전송하지 않음";
                }
                catch (Exception e) { status=e.Message; }
            }
        }
        using (new EditorGUI.DisabledScope(busy || attempted || request==null))
            if (GUILayout.Button("2. Gateway에 한 번 전송 + 결과 구독"))
                if (EditorUtility.DisplayDialog("Gateway 실제 진단 요청", "진단 및 후보별 TCAD 실행이 시작될 수 있습니다. 새 요청을 한 건 전송합니다. 승인·레시피 적용은 수행하지 않습니다.","전송","취소")) _=Send();
        using (new EditorGUI.DisabledScope(busy || state==null))
            if (GUILayout.Button("3. 결과만 재접속 (마지막 sequence 이후, 요청 재전송 없음)")) _=Resume();
        if (busy && GUILayout.Button("수신 중지 (서버 작업은 계속됨)")) lifetime?.Cancel();
        if (!busy && GUILayout.Button("저장된 테스트 다시 열기 (요청 전송 없이 처음부터 재생)"))
        {
            string path=EditorUtility.OpenFilePanel("Runs 폴더의 request.json 선택",Path.GetFullPath("Tools/Gateway/AsyncTcadTest/Runs"),"json");
            if (!string.IsNullOrEmpty(path))
            {
                try
                {
                    var savedRequest=JObject.Parse(File.ReadAllText(path));
                    string folder=Path.GetDirectoryName(path);
                    var ack=JObject.Parse(File.ReadAllText(Path.Combine(folder,"accepted.json")));
                    if ((string)ack["request_id"]!=(string)savedRequest["request_id"]) throw new FormatException("Saved receipt mismatch");
                    state=new AsyncTcadContract.State((string)savedRequest["run_id"],(string)savedRequest["request_id"],(string)ack["job_id"]);
                    request=savedRequest; evidence=folder; attempted=true;
                    status="저장된 ID 복원 · 결과만 재접속을 누르면 sequence 0부터 상태 복원 · 진단 재전송 없음";
                }
                catch(Exception e) { status=e.Message; }
            }
        }
        if (!busy && GUILayout.Button("새 테스트 준비 (이전 작업 취소 아님)")) { attempted=false; request=null; state=null; output=""; }
        if (GUILayout.Button("오프라인 계약 테스트 실행"))
        {
            try { status=AsyncTcadChecks.Run(); Debug.Log(status); }
            catch (Exception e) { status=e.ToString(); Debug.LogError(status); }
        }
        EditorGUILayout.HelpBox(status,MessageType.None);
        if (state!=null) EditorGUILayout.LabelField("마지막 sequence / 후보 수",state.Sequence+" / "+state.Candidates.Count);
        scroll=EditorGUILayout.BeginScrollView(scroll);
        EditorGUILayout.SelectableLabel(output,GUILayout.MinHeight(350));
        EditorGUILayout.EndScrollView();
    }
    async Task Send()
    {
        busy=true; attempted=true; lifetime=new CancellationTokenSource();
        try
        {
            File.WriteAllText(Path.Combine(evidence,"send-attempted.txt"),DateTime.UtcNow.ToString("O"));
            var ack=await AsyncTcadSocket.SendOnce(origin,token,request,lifetime.Token);
            File.WriteAllText(Path.Combine(evidence,"accepted.json"),ack.ToString());
            state=new AsyncTcadContract.State((string)request["run_id"],(string)request["request_id"],(string)ack["job_id"]);
            status="접수 확인 · 완료 아님 · Gateway DB 이벤트 수신 중";
            await Listen();
        }
        catch (OperationCanceledException) { status="수신 중지/시간 초과 · 접수 여부는 저장된 ID로 확인 · 자동 재전송 없음"; }
        catch (Exception e) { status=e.GetType().Name+": "+e.Message+" · 자동 재전송 없음"; }
        finally { busy=false; lifetime.Dispose(); lifetime=null; Repaint(); }
    }
    async Task Resume()
    {
        busy=true; lifetime=new CancellationTokenSource();
        try { await Listen(); }
        catch (OperationCanceledException) { status="수신 중지 · 서버 작업 취소 아님"; }
        catch (Exception e) { status=e.GetType().Name+": "+e.Message; }
        finally { busy=false; lifetime.Dispose(); lifetime=null; Repaint(); }
    }
    async Task Listen()
    {
        using (var socket=await AsyncTcadSocket.ConnectStream(origin,state.Run,state.Sequence,lifetime.Token))
        {
            while (!lifetime.IsCancellationRequested)
            {
                var item=await AsyncTcadSocket.Receive(socket,lifetime.Token);
                if (state.Accept(item))
                {
                    File.AppendAllText(Path.Combine(evidence,"events.jsonl"),item.ToString(Formatting.None)+Environment.NewLine);
                    output=item.ToString(Formatting.Indented);
                    status=(string)item["event_type"]+" · 검증 성공과 관리자 승인은 별개";
                    if ((string)item["event_type"]=="diagnosis.completed")
                    {
                        string route=(string)state.Diagnosis?["result_payload"]?["compensation"]?["route"];
                        status="진단 결과 수신 · route="+(route??"없음")+" · 자동 승인/적용 없음";
                        if(route=="apply") status+=" · TCAD 후보가 없을 수 있음 / Gateway 검증 정책과 확인 필요";
                    }
                }
                File.WriteAllText(Path.Combine(evidence,"cursor.json"),new JObject { ["run_id"]=state.Run, ["request_id"]=state.Request, ["job_id"]=state.Job, ["after_sequence"]=state.Sequence }.ToString());
                Repaint();
            }
        }
    }
}
