using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Security.Cryptography;
using UnityEngine;
using UnityEngine.Networking;

// Review notifications open this local UI; only a confirmed Gateway decision can stage setpoints.
public sealed class GatewayTcadApprovalView : MonoBehaviour
{
    // shortcut: local demo lock only; production administrator identity must be checked by Gateway.
    public sealed class AdminGate
    {
        string allowedScope;
        public bool Authorize(string password,string scope)
        {
            Clear();if(string.IsNullOrWhiteSpace(scope)||string.IsNullOrEmpty(password)||password.Length>32)return false;
            using(var hash=new Rfc2898DeriveBytes(password,Encoding.UTF8.GetBytes("Unity-TCAD-admin-demo-v1"),100000,HashAlgorithmName.SHA256))
            {
                byte[] expected=Convert.FromBase64String("E18Ij2cJCCxfkAk5lwMRw5YN051214wVOfV3uMW0ros="),actual=hash.GetBytes(32);
                int mismatch=0;for(int i=0;i<expected.Length;i++)mismatch|=expected[i]^actual[i];
                if(mismatch!=0)return false;
            }
            allowedScope=scope;return true;
        }
        public bool Consume(string scope){bool ok=allowedScope!=null&&allowedScope==scope;Clear();return ok;}
        public void Clear(){allowedScope=null;}
    }
    class Review
    {
        public GatewayInspectionBridge.Job job;
        public GatewayTcadApprovalProtocol.Proposal proposal;
        public int selected;
        public bool uncertain;
        public string confirmedScope;
    }
    GatewayInspectionBridge bridge;GatewayApprovedRecipe recipes;
    readonly Dictionary<string,Review> reviews=new Dictionary<string,Review>();
    Review active;bool open,busy;string actor="",status="TCAD 후보 조회 대기";Vector2 scroll;
    Review adminReview;string adminScope,adminActor,password="",adminError="";bool adminApprove;
    readonly AdminGate adminGate=new AdminGate();
    public int LastWindowPaintFrame{get;private set;}=-1;
    public int LastAdminPaintFrame{get;private set;}=-1;
    static string Scope(Review r,bool approve,string actor)
    {
        if(approve&&(r.selected<0||r.selected>=r.proposal.candidates.Length))return null;
        return r.proposal.proposal_id+"\n"+r.job.cycle.Run+"\n"+(approve?r.proposal.candidates[r.selected].tcad_request_id+"\n"+JsonUtility.ToJson(r.proposal.candidates[r.selected].process_parameters):"rejected")+"\n"+actor;
    }
    static void SelectCandidate(Review review,int selected){if(review.selected!=selected){review.selected=selected;review.confirmedScope=null;}}
    void CancelAdmin(){adminGate.Clear();adminReview=null;password="";adminError="";adminScope=null;adminActor=null;}
    void OnDisable(){CancelAdmin();}
    void BeginAdmin(Review review,bool approve)
    {
        if(approve&&review.confirmedScope!=Scope(review,true,actor.Trim())){status="선택한 후보의 실제 TCAD 결과 확인이 필요합니다.";return;}
        CancelAdmin();adminReview=review;adminApprove=approve;adminActor=actor.Trim();adminScope=Scope(review,approve,adminActor);
    }
    void ConfirmAdmin()
    {
        var r=adminReview;if(r==null)return;
        if(busy||r.uncertain||r.proposal.status!="review_required"||Scope(r,adminApprove,adminActor)!=adminScope||
           adminApprove&&(r.proposal.candidates.Length<=r.selected||!GatewayTcadApprovalProtocol.Eligible(r.proposal.candidates[r.selected])))
        {CancelAdmin();status="후보 상태가 변경되었습니다. 다시 조회 후 승인하세요.";return;}
        if(adminApprove&&r.confirmedScope!=adminScope){CancelAdmin();status="실제 TCAD 확인이 초기화됐습니다. 다시 확인하세요.";return;}
        bool verified=adminGate.Authorize(password,adminScope);password="";
        if(!verified){adminError="비밀번호가 올바르지 않습니다.";return;}
        string scope=adminScope,by=adminActor;bool approve=adminApprove;
        adminReview=null;adminScope=null;adminActor=null;adminError="";
        StartCoroutine(Decide(r,approve,by,scope));
    }
    public static GatewayTcadApprovalView For(GatewayInspectionBridge bridge)
    {
        var view=bridge.GetComponent<GatewayTcadApprovalView>();if(!view)view=bridge.gameObject.AddComponent<GatewayTcadApprovalView>();
        view.bridge=bridge;return view;
    }
    GatewayApprovedRecipe Recipes()
    {
        if(!recipes)recipes=GetComponent<GatewayApprovedRecipe>()??gameObject.AddComponent<GatewayApprovedRecipe>();
        recipes.Bind(FindAnyObjectByType<IonImplantCycle>(),FindAnyObjectByType<IntegratedOxidationCycle>());return recipes;
    }
    public void Show(GatewayInspectionBridge.Job job){open=true;if(!busy)StartCoroutine(Query(job));}
    public bool Observe(GatewayInspectionBridge.Job job,string raw)
    {
        var e=JsonUtility.FromJson<GatewayTcadApprovalProtocol.Event>(raw);
        if(e?.event_type!="tcad.verification.review_required"&&e?.event_type!="tcad.verification.decided")return false;
        if(!Guid.TryParse(e.event_id,out _)||e.sequence<=job.cycle.Sequence)throw new ArgumentException("검토 이벤트 식별자/순서 오류");
        if(e.run_id!=job.cycle.Run||job.cycle.Route!="tcad_verify"||!Guid.TryParse(e.payload?.proposal_id,out _))throw new ArgumentException("검토 이벤트 검사 연결 오류");
        job.cycle.ObserveApprovalContext(raw);
        if(job.cycle.DecisionReceived&&job.cycle.ProposalId==e.payload.proposal_id)return true;
        job.cycle.ObserveReview(e.payload.proposal_id);open=true;
        if(e.event_type=="tcad.verification.review_required")
        {status="TCAD 검증 완료 · 후보 조회 중";if(!busy)StartCoroutine(Query(job));return true;}
        var p=e.payload;string decision=p.decision??p.status;
        if(decision=="rejected"){job.cycle.ObserveDecision(p.proposal_id,"rejected");status="Gateway 반려 확인 · 공정 설정 미변경";return true;}
        if(decision=="approved")
        {
            // Remote decisions require an explicit selected ID and parameters, never infer from an array.
            if(reviews.TryGetValue(p.proposal_id,out var review)&&review.proposal!=null&&Guid.TryParse(p.selected_tcad_request_id,out _)&&!string.IsNullOrWhiteSpace(p.decided_by))
            {
                var selected=review.proposal.candidates.FirstOrDefault(c=>c.tcad_request_id==p.selected_tcad_request_id);
                var body=JsonUtility.ToJson(new GatewayTcadApprovalProtocol.DecisionResponse{proposal_id=p.proposal_id,status="approved",process_parameters=p.process_parameters});
                var receipt=GatewayTcadApprovalProtocol.Confirm(body,review.proposal,selected,job.cycle.Run,job.request.lot_id,p.decided_by);
                Apply(review,receipt,body);return true;
            }
            status="다른 클라이언트 승인 수신 · 선택 후보/원문 확인 전 적용 대기";
            if(!busy)StartCoroutine(Query(job));return true;
        }
        status="Gateway 결정 형식 확인 필요 · 공정 설정 미변경";return true;
    }
    IEnumerator Query(GatewayInspectionBridge.Job job)
    {
        if(job?.cycle==null){status="먼저 이 Play에서 보낸 검사 RUN을 선택하세요.";yield break;}
        if(string.IsNullOrWhiteSpace(bridge.Token)){status="Gateway 요청 토큰을 입력한 뒤 후보를 다시 조회하세요.";yield break;}
        busy=true;
        using(var request=UnityWebRequest.Get(new UriBuilder(GatewayTcadApprovalProtocol.Address(job.streamAddress,"")){Query="status=review_required"}.Uri.AbsoluteUri))
        {
            request.SetRequestHeader("X-Unity-Token",bridge.Token);request.timeout=15;yield return request.SendWebRequest();
            try
            {
                if(request.result!=UnityWebRequest.Result.Success)throw new IOException("후보 조회 실패 · HTTP "+request.responseCode);
                var list=GatewayTcadApprovalProtocol.ReadList(request.downloadHandler.text);
                var group=list.proposals.FirstOrDefault(p=>p.run_id==job.cycle.Run&&p.job_id==job.cycle.DiagnosisJob&&p.status=="review_required"&&(job.cycle.ProposalId==null||p.proposal_id==job.cycle.ProposalId));
                if(group==null){status="해당 RUN의 검토 대기 후보가 없습니다. 이미 결정됐거나 서버 저장 확인이 필요합니다.";active=null;}
                else
                {
                    if(!reviews.TryGetValue(group.proposal_id,out active)){active=new Review{job=job};reviews[group.proposal_id]=active;}
                    active.confirmedScope=null;active.proposal=group;active.selected=Math.Min(active.selected,Math.Max(0,group.candidates.Length-1));
                    job.cycle.ObserveReview(group.proposal_id);status="후보를 선택하고 승인자명을 입력하세요. 규격 미확인·NG 후보는 적용하지 않습니다.";
                }
            }
            catch(Exception error){status=error.Message;}
        }
        busy=false;
    }
    IEnumerator Decide(Review review,bool approve,string decidedBy,string authorizedScope)
    {
        if(!adminGate.Consume(authorizedScope)||authorizedScope!=Scope(review,approve,decidedBy)||approve&&review.confirmedScope!=authorizedScope)
        {status="관리자 승인 필요 · 비밀번호를 다시 입력하세요.";yield break;}
        var group=review.proposal;var selected=group.candidates.Length>review.selected?group.candidates[review.selected]:null;
        string body=GatewayTcadApprovalProtocol.Body(decidedBy,selected?.tcad_request_id,approve);busy=true;
        using(var request=new UnityWebRequest(GatewayTcadApprovalProtocol.Address(review.job.streamAddress,"/"+group.proposal_id+"/decision"),"POST"))
        {
            request.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));request.downloadHandler=new DownloadHandlerBuffer();request.timeout=20;
            request.SetRequestHeader("Content-Type","application/json");request.SetRequestHeader("X-Unity-Token",bridge.Token);yield return request.SendWebRequest();
            try
            {
                if(request.result!=UnityWebRequest.Result.Success){review.uncertain=true;throw new IOException("결정 접수 여부 확인 필요 · HTTP "+request.responseCode+" / 자동 재전송·적용 없음");}
                string raw=request.downloadHandler.text;
                if(approve)
                {
                    var receipt=GatewayTcadApprovalProtocol.Confirm(raw,group,selected,review.job.cycle.Run,review.job.request.lot_id,decidedBy);Apply(review,receipt,raw);
                }
                else
                {
                    var response=JsonUtility.FromJson<GatewayTcadApprovalProtocol.DecisionResponse>(raw);
                    if(response?.proposal_id!=group.proposal_id||response.status!="rejected"||response.process_parameters!=null)throw new ArgumentException("Gateway 반려 응답 형식 확인 필요");
                    review.job.cycle.ObserveDecision(group.proposal_id,"rejected");group.status="rejected";status="반려 완료 · 보정값 적용 없음";Save(group.proposal_id,raw);
                }
            }
            catch(Exception error){review.uncertain=true;status=error.Message;}
        }
        busy=false;
    }
    void Apply(Review review,GatewayApprovedRecipe.Approval receipt,string raw)
    {
        GatewayApprovedRecipe.Validate(receipt,review.job.cycle.Run,review.job.request.lot_id,review.proposal.proposal_id,receipt.selected_tcad_request_id);
        Save(receipt.proposal_id,raw);
        File.WriteAllText(Path.Combine(Application.dataPath,"../Tools/Gateway/Approvals",receipt.proposal_id+".context.json"),JsonUtility.ToJson(receipt,true));
        if(review.confirmedScope!=Scope(review,true,receipt.decided_by))
        {
            review.job.cycle.ObserveDecision(receipt.proposal_id,"approved");review.proposal.status="approved";
            status=review.job.state=review.job.cycle.TestTcad?"시험 승인 응답 확인 · fake 결과 / 실제 보정값 미적용":"승인 응답 확인 · 실제 실행 모드·적용 허용 확인 전 미적용";
            return;
        }
        receipt.real_tcad_confirmed_by_operator=true;receipt.confirmed_at=DateTimeOffset.UtcNow.ToString("O");
        var service=Recipes();service.Stage(receipt,receipt.run_id,receipt.lot_id,receipt.proposal_id,receipt.selected_tcad_request_id);
        review.job.cycle.ObserveDecision(receipt.proposal_id,"approved");review.proposal.status="approved";review.job.state=service.Status;status=service.Status+" · 실제 TCAD 여부: 관리자 확인 / 다음 LOT부터";
        File.WriteAllText(Path.Combine(Application.dataPath,"../Tools/Gateway/Approvals",receipt.proposal_id+".context.json"),JsonUtility.ToJson(receipt,true));
    }
    static void Save(string id,string raw)
    {string dir=Path.Combine(Application.dataPath,"../Tools/Gateway/Approvals");Directory.CreateDirectory(dir);File.WriteAllText(Path.Combine(dir,id+".decision.json"),raw);}
    Texture2D opaqueBlack;
    GUIStyle opaqueWindow;
    GUIStyle BlackWindow()
    {
        if(opaqueWindow!=null)return opaqueWindow;
        opaqueBlack=new Texture2D(1,1);opaqueBlack.hideFlags=HideFlags.HideAndDontSave;
        opaqueBlack.SetPixel(0,0,Color.black);opaqueBlack.Apply();
        opaqueWindow=new GUIStyle(GUI.skin.window);
        foreach(var state in new[]{opaqueWindow.normal,opaqueWindow.hover,opaqueWindow.active,opaqueWindow.focused,opaqueWindow.onNormal,opaqueWindow.onHover,opaqueWindow.onActive,opaqueWindow.onFocused})
        {state.background=opaqueBlack;state.scaledBackgrounds=null;state.textColor=Color.white;}
        return opaqueWindow;
    }
    void OnDestroy(){if(opaqueBlack)Destroy(opaqueBlack);}
    void OnGUI()
    {
        if(!open)return;var old=GUI.matrix;float scale=Mathf.Min(Screen.width/1000f,Screen.height/700f);GUI.matrix=Matrix4x4.Scale(Vector3.one*scale);
        var previousColor=GUI.color;var previousContent=GUI.contentColor;var previousBackground=GUI.backgroundColor;bool previousEnabled=GUI.enabled;
        GUI.color=GUI.contentColor=GUI.backgroundColor=Color.white;
        var windowStyle=BlackWindow();
        GUI.DrawTexture(new Rect(35,45,930,600),opaqueBlack);
        GUI.enabled=adminReview==null;
        GUI.Window(196411,new Rect(35,45,930,600),Draw,"TCAD 검증 후보 — 승인 및 공정 설정 적용",windowStyle);GUI.enabled=true;
        GUI.BringWindowToFront(196411);
        if(Event.current.type==EventType.Repaint)LastWindowPaintFrame=Time.frameCount;
        if(adminReview!=null)
        {
            GUI.DrawTexture(new Rect(255,195,490,285),opaqueBlack);
            GUI.ModalWindow(196412,new Rect(255,195,490,285),DrawAdmin,"관리자 승인 필요",windowStyle);
            GUI.BringWindowToFront(196412);
            if(Event.current.type==EventType.Repaint)LastAdminPaintFrame=Time.frameCount;
        }
        GUI.matrix=old;GUI.color=previousColor;GUI.contentColor=previousContent;GUI.backgroundColor=previousBackground;GUI.enabled=previousEnabled;
    }
    void DrawAdmin(int id)
    {
        var r=adminReview;
        GUILayout.Space(12);GUILayout.Label(adminApprove?("실제 TCAD 여부: 관리자 확인 · 다음 LOT부터 적용"):"보정안을 반려하려면 관리자 승인이 필요합니다.");
        GUILayout.Label("LOT: "+r.job.request.lot_id+" / 승인자: "+adminActor);
        GUILayout.Label(adminApprove?"선택 후보: "+(r.selected<r.proposal.candidates.Length?(r.proposal.candidates[r.selected].candidate_index+1).ToString():"상태 변경됨"):"결정: 반려");
        GUILayout.Space(10);GUILayout.Label("관리자 비밀번호");password=GUILayout.PasswordField(password,'●',32,GUILayout.Height(30));
        var color=GUI.contentColor;GUI.contentColor=Color.red;GUILayout.Label(adminError);GUI.contentColor=color;
        GUILayout.BeginHorizontal();if(GUILayout.Button("취소",GUILayout.Height(32)))CancelAdmin();
        if(GUILayout.Button(adminApprove?"승인 확인":"반려 확인",GUILayout.Height(32)))ConfirmAdmin();GUILayout.EndHorizontal();
        var e=Event.current;if(e.type==EventType.KeyDown&&e.keyCode==KeyCode.Escape){CancelAdmin();e.Use();}
    }
    void Draw(int id)
    {
        GUILayout.BeginHorizontal();GUILayout.Label(status,GUILayout.MaxWidth(760));if(GUILayout.Button("닫기",GUILayout.Width(70)))open=false;GUILayout.EndHorizontal();
        if(active==null){GUILayout.Label("Gateway 검토 신호를 기다리거나 분석 화면에서 후보 조회를 선택하세요.");return;}
        var r=active;var g=r.proposal;
        GUILayout.Label(r.job.request.lot_id+" / 검사 "+r.job.inspectionId+" / RUN "+g.run_id);
        GUILayout.Label("시연용 · 실제 TCAD 여부는 관리자가 확인합니다. unity_mode는 출처 판정에 사용하지 않습니다.");
        GUILayout.Label(g.candidates.Any(GatewayTcadApprovalProtocol.Eligible)?"정상 후보를 선택해 승인하거나 반려하세요.":"정상 후보 없음 · 승인 불가 / 반려 필요");
        GUILayout.Label("도즈 cm⁻² · 에피 cm⁻³ · 산화막 µm (설비 표시는 nm) · 전기특성 V / µS/µm / µA/µm / V");
        scroll=GUILayout.BeginScrollView(scroll,GUILayout.Height(310));
        for(int i=0;i<g.candidates.Length;i++)
        {
            var c=g.candidates[i];var p=c.process_parameters;var e=c.result_payload;bool eligible=GatewayTcadApprovalProtocol.Eligible(c);
            GUI.enabled=!busy&&g.status=="review_required";if(GUILayout.Toggle(r.selected==i,"후보 "+(c.candidate_index+1)+" · "+(eligible?"정상":"불가")+" / "+(c.spec_verdict?.overall??"판정 미수신"))&&r.selected!=i){SelectCandidate(r,i);}GUI.enabled=true;
            GUILayout.Label(p==null?"공정값 미수신":$"도즈 {p.body_dose:0.000E+00} / 에피 {p.epi_doping:0.000E+00} / 산화막 {p.oxide_thickness:G8} µm = {p.oxide_thickness*1000:G8} nm");
            GUILayout.Label(e==null?"TCAD 결과 미수신":$"Vth {e.vth:F4} V / BV {(c.spec_verdict?.overall=="bv_unconfirmed"?"미확인":e.bv.ToString("F3")+" V")} / gm {e.gm:G5} / Id {e.id_on:G5}");
            GUILayout.Label(eligible?(GatewayTcadApprovalProtocol.Positive(p)?"서버 판정 정상 · 승인 선택 가능":"서버 판정 정상 · 공정값 누락으로 전송 보류"):"서버 판정 불가 · 승인 선택 불가");GUILayout.Space(10);
        }
        GUILayout.EndScrollView();GUILayout.BeginHorizontal();GUILayout.Label("승인자",GUILayout.Width(60));actor=GUILayout.TextField(actor,GUILayout.Width(270));GUILayout.EndHorizontal();
        string confirmationScope=Scope(r,true,actor.Trim());
        bool confirmed=r.confirmedScope!=null&&r.confirmedScope==confirmationScope;
        bool check=GUILayout.Toggle(confirmed,"선택 후보가 실제 TCAD 결과임을 확인했습니다");
        r.confirmedScope=check?confirmationScope:null;
        GUILayout.BeginHorizontal();
        bool can=!busy&&!r.uncertain&&g.status=="review_required"&&!string.IsNullOrWhiteSpace(actor)&&!string.IsNullOrWhiteSpace(bridge.Token)&&(!recipes||recipes.Pending==null);
        GUI.enabled=can&&r.confirmedScope!=null&&g.candidates.Length>r.selected&&GatewayTcadApprovalProtocol.Eligible(g.candidates[r.selected])&&GatewayTcadApprovalProtocol.Positive(g.candidates[r.selected].process_parameters);if(GUILayout.Button("관리자 승인 요청"))BeginAdmin(r,true);
        GUI.enabled=can;if(GUILayout.Button("보정안 반려"))BeginAdmin(r,false);GUI.enabled=!busy;if(GUILayout.Button("다시 조회"))StartCoroutine(Query(r.job));GUI.enabled=true;GUILayout.EndHorizontal();
        GUILayout.Label(recipes?recipes.Status:"승인 전 미적용 · 동작 중에는 적용 대기 · 검사 기준/기록/HOLD는 변경하지 않습니다.");
        GUILayout.Label("시뮬레이션 공정 설정 적용입니다. 기존 CSV·전기특성 값은 새 측정이나 재검증 결과로 대체하지 않습니다.");
    }
}
