using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading.Tasks;
using UnityEngine;

// Read-only Jetson test results. This component never changes recipes or LOT disposition.
public partial class ProcessAnalysisView : MonoBehaviour
{
    [Serializable] public class Candidate { public string name; public float probability; }
    [Serializable] public class Measurement {public float vth,gm,id4v,bv;}
    [Serializable] public class Units {public string vth="V",gm="A/V/um",id4v="A/um",bv="V";}
    [Serializable] public class Header
    {public string request_id,lot_id,baseline_version,data_source="synthetic";public Units units=new Units();public int n_wafers;public long sent_at_ms;}
    [Serializable] public class Input : Header {public Measurement measurement;}
    [Serializable] public class Sample {public string name,title;public int n_wafers;public bool has_bv;public Measurement measurement;}
    [Serializable] class Samples {public string baseline_version;public Sample[] cases;}
    [Serializable] class State {public string state,request_id,lot_id,detail;}
    [Serializable] class Transport {public int version;public string type,source,target,message_id,code;public State payload;}
    [Serializable] public class Payload
    {
        public string lot_id,run_id,proposal_id,baseline_version,model_version,data_source,delivery,mode,request_id;
        public string decision,top_cause,recommendation,warning,tcad_status;
        public bool decided,applied;
        public float top_probability,dose_factor,oxide_factor,estimated_dose,estimated_epi,estimated_oxide,duration_seconds;
        public long generated_at_ms,sent_at_ms;
        public Candidate[] basic_candidates;
        public Input input;
    }
    [Serializable] class Envelope
    {public int version;public string type,source,target,message_id;public Payload payload;}
    public static ProcessAnalysisView Instance {get;private set;}
    public readonly List<Payload> History=new List<Payload>();
    readonly Dictionary<string,string> seen=new Dictionary<string,string>();
    readonly Queue<string> order=new Queue<string>();
    public int AcceptedCount {get;private set;}
    public int SelectedIndex {get;private set;}
    public bool WindowOpen {get;private set;}
    public Payload Current=>History.Count==0?null:History[Mathf.Clamp(SelectedIndex,0,History.Count-1)];
    AoiWebSocketClient client;
    Font font;
    Rect window=new Rect(130,12,1020,688);
    Samples samples;
    int sampleIndex;
    Input pending;
    float requestStarted,workerSeen=-1000;
    bool workerReady;
    string lotContext;
    public event Action<Payload> ResultReceived;
    public event Action<string,string> RequestFailed;
    public string PendingRequestId=>pending?.request_id;
    public bool RequestPending=>pending!=null;
    public bool CanRequest=>Connected&&!RequestPending&&workerReady&&Time.realtimeSinceStartup-workerSeen<15;
    public string RequestState {get;private set;}="시험값 선택 후 새 분석 요청";
    public string LastCompletedRequest {get;private set;}
    public bool Connected=>client&&client.Connected;
    public string LastError {get;private set;}
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    static void ResetStatic(){Instance=null;}
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Attach()
    {
        var socket=FindAnyObjectByType<AoiWebSocketClient>();
        if(socket&&!socket.GetComponent<ProcessAnalysisView>())socket.gameObject.AddComponent<ProcessAnalysisView>();
        if(socket&&!socket.GetComponent<LotProcessAnalysis>())socket.gameObject.AddComponent<LotProcessAnalysis>();
        if(socket&&!socket.GetComponent<GatewayInspectionBridge>())socket.gameObject.AddComponent<GatewayInspectionBridge>();
        var view=socket?socket.GetComponent<ProcessAnalysisView>():null;
        if(view){view.InitializeView();view.ionInspection=null;view.ionInspections.Clear();}
    }
    void Awake(){InitializeView();}
    void InitializeView(){Instance=this;client=GetComponent<AoiWebSocketClient>();var asset=Resources.Load<TextAsset>("ProcessAnalysisSamples");if(asset)samples=JsonUtility.FromJson<Samples>(asset.text);}
    void Update()
    {
        if(pending!=null&&(!Connected||Time.realtimeSinceStartup-requestStarted>210))
        FailPending(Connected?"응답 시간 초과 · 계산 결과 확인 필요":"서버 연결 끊김 · 요청 결과 확인 필요");
        PumpIonDirect();
    }
    void FailPending(string reason)
    {if(pending==null)return;var id=pending.request_id;pending=null;RequestState=reason;FailIonDirect(id,reason);RequestFailed?.Invoke(id,reason);}
    public bool HandleTransport(string json)
    {
        var e=JsonUtility.FromJson<Transport>(json);
        if(e.type=="error"||e.type=="ack")
        {
            if(pending==null||e.message_id!=pending.request_id)return e.message_id!=null&&e.message_id.StartsWith("REQ-",StringComparison.Ordinal);
            if(e.type=="error")FailPending("요청 전달 실패: "+e.code);
            else RequestState="요청 전달됨 · Jetson 계산 대기";
            return true;
        }
        if(e.type!="process_status")return false;
        if(e.version!=1||e.source!="process_ai"||e.target!="unity"||e.payload==null)return true;
        var s=e.payload;
        if(s.state=="ready"){workerSeen=Time.realtimeSinceStartup;workerReady=s.detail=="ready";return true;}
        if(pending!=null&&s.request_id==pending.request_id&&s.lot_id==pending.lot_id)
        {
            if(s.state=="running")RequestState="Jetson 새 진단 계산 중…";
            if(s.state=="failed")FailPending(s.detail);
        }
        return true;
    }
    public Task<bool> RequestSample(int index)
    {
        if(samples?.cases==null||index<0||index>=samples.cases.Length||pending!=null||!Connected)return Task.FromResult(false);
        sampleIndex=index;
        var s=samples.cases[index];
        return RequestInput(NewInput("TEST-"+s.name,samples.baseline_version,s.n_wafers,s.measurement),s.has_bv);
    }
    public static Input NewInput(string lotId,string baseline,int count,Measurement m)
    {return new Input{request_id="REQ-"+Guid.NewGuid().ToString("N"),lot_id=lotId,baseline_version=baseline,n_wafers=count,measurement=new Measurement{vth=m.vth,gm=m.gm,id4v=m.id4v,bv=m.bv}};}
    public async Task<bool> RequestInput(Input input,bool hasBv)
    {
        if(input==null||pending!=null||!Connected||!Id(input.request_id)||!Id(input.lot_id)||!Id(input.baseline_version)||input.data_source!="synthetic"||input.n_wafers<1||input.n_wafers>10000)return false;
        var m=input.measurement;
        if(m==null||!Number(m.vth,-100,100)||!Number(m.gm,1e-15f,1)||!Number(m.id4v,1e-15f,1)||(hasBv&&!Number(m.bv,.001f,10000)))return false;
        input=JsonUtility.FromJson<Input>(JsonUtility.ToJson(input));input.sent_at_ms=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();input.units=new Units();
        if(!hasBv)input.measurement.bv=0;
        pending=input;requestStarted=Time.realtimeSinceStartup;RequestState="요청 전송 중…";
        var id=input.request_id;
        string header=JsonUtility.ToJson(new Header{request_id=id,lot_id=input.lot_id,baseline_version=input.baseline_version,n_wafers=input.n_wafers,sent_at_ms=input.sent_at_ms});header=header.Substring(0,header.Length-1);
        string N(float v)=>v.ToString("R",CultureInfo.InvariantCulture);
        // Unity JsonUtility has no nullable number; missing BV is explicitly null on the wire.
        string measurement="{\"vth\":"+N(m.vth)+",\"gm\":"+N(m.gm)+",\"id4v\":"+N(m.id4v)+",\"bv\":"+(hasBv?N(m.bv):"null")+"}";
        string body=header+",\"measurement\":"+measurement+"}";
        string packet="{\"version\":1,\"type\":\"process_request\",\"message_id\":\""+id+"\",\"payload\":"+body+"}";
        bool sent=await client.SendProcessRequest(packet);
        if(!sent&&pending==input)FailPending("전송 실패 · 서버 연결을 확인해 주세요");
        return sent;
    }
    static bool Number(float v,float lo,float hi)=>!float.IsNaN(v)&&!float.IsInfinity(v)&&v>=lo&&v<=hi;
    static bool Id(string value)=>!string.IsNullOrWhiteSpace(value)&&value.Length<=128&&Array.TrueForAll(value.ToCharArray(),c=>!char.IsControl(c));
    public bool Accept(string json)
    {
        try
        {
            var message=JsonUtility.FromJson<Envelope>(json);var p=message?.payload;
            if(message==null||message.version!=1||message.type!="process_analysis"||message.source!="process_ai"||message.target!="unity"||!Id(message.message_id)||p==null)throw new ArgumentException();
            if(seen.TryGetValue(message.message_id,out string prior))
            {if(prior!=json)throw new ArgumentException();return false;}
            if(!Id(p.lot_id)||!Id(p.run_id)||!Id(p.proposal_id)||!Id(p.baseline_version)||!Id(p.model_version))throw new ArgumentException();
            if(p.data_source!="synthetic"||(p.delivery!="replay"&&p.delivery!="computed")||(p.mode!="gp_tabpfn"&&p.mode!="gp_only")||p.tcad_status!="not_run"||p.applied)throw new ArgumentException();
            if(p.delivery=="computed"&&(pending==null||p.request_id!=pending.request_id||p.lot_id!=pending.lot_id||p.input==null||JsonUtility.ToJson(p.input)!=JsonUtility.ToJson(pending)))throw new ArgumentException();
            string[] causes={"정상","도즈","에피","도즈+에피","산화막","도즈+산화막","에피+산화막","도즈+에피+산화막"};
            if(Array.IndexOf(causes,p.top_cause)<0||!Number(p.top_probability,0,1)||p.decided!=(p.top_probability>=.70f))throw new ArgumentException();
            string expected=!p.decided?"ambiguous":p.top_cause=="정상"?"normal":"diagnosed";
            if(p.decision!=expected||!Number(p.dose_factor,.84999f,1.15001f)||!Number(p.oxide_factor,.84999f,1.15001f)||!Number(p.duration_seconds,0,3600))throw new ArgumentException();
            if(!Number(p.estimated_dose,.01f,10)||!Number(p.estimated_epi,.01f,10)||!Number(p.estimated_oxide,.01f,10))throw new ArgumentException();
            if(p.recommendation==null||p.recommendation.Length>500||p.warning==null||p.warning.Length>500||p.basic_candidates==null||p.basic_candidates.Length!=8)throw new ArgumentException();
            float total=0;var names=new HashSet<string>();
            foreach(var c in p.basic_candidates)
            {if(c==null||Array.IndexOf(causes,c.name)<0||!names.Add(c.name)||!Number(c.probability,0,1))throw new ArgumentException();total+=c.probability;}
            if(Mathf.Abs(total-1)>.0001f||p.generated_at_ms<=0||p.sent_at_ms<=0||p.generated_at_ms>p.sent_at_ms+120000)throw new ArgumentException();
            seen[message.message_id]=json;order.Enqueue(message.message_id);
            if(order.Count>128)seen.Remove(order.Dequeue());
            int index=History.FindIndex(x=>x.proposal_id==p.proposal_id);
            if(index>=0)History[index]=p;else{if(History.Count==32)History.RemoveAt(0);History.Add(p);index=History.Count-1;}
            SelectedIndex=index;AcceptedCount++;LastError=null;
            if(p.delivery=="computed"){LastCompletedRequest=p.request_id;pending=null;RequestState="새 진단 완료 · "+(p.mode=="gp_tabpfn"?"고정밀":"기본 GP")+" · TCAD 검증 대기";ReceiveIonDirect(p);ResultReceived?.Invoke(p);}
            return true;
        }
        catch(Exception){LastError="공정 분석 메시지 형식 확인 필요";return false;}
    }
    public void SelectResult(int index){if(index>=0&&index<History.Count)SelectedIndex=index;}
    public void Open()
    {
        if(FactoryControlBar.Selected==FactoryControlBar.Equipment.Implanter&&OpenIonResult(FindAnyObjectByType<IonImplantCycle>()))return;
        selectedFullCycle=null;ionInspection=null;lotContext=null;WindowOpen=true;
    }
    public void OpenLot(string lotId){selectedFullCycle=null;ionInspection=null;lotContext=lotId;WindowOpen=true;}
    public static string MonitorSummary(bool dose)
    {
        var view=Instance;var p=view?view.Current:null;
        if(p==null)return "Jetson 공정 분석 수신 대기 · 실제 TCAD 미연결";
        return (view.Connected?"Jetson 시험 결과":"마지막 수신 결과 · 연결 끊김")+" | "+(dose?"도즈 ×"+p.dose_factor.ToString("F3"):"산화막 ×"+p.oxide_factor.ToString("F3"))+"\n"+(p.decided?"원인 후보: "+p.top_cause:"구분 불가 · 추가 확인 필요")+" | TCAD 검증 대기";
    }
    void OnGUI()
    {
        if(!Application.isPlaying)return;
        if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Arial"},18);
        var matrix=GUI.matrix;int depth=GUI.depth;GUI.depth=-50;float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);GUI.matrix=Matrix4x4.Scale(Vector3.one*scale);
        var selected=FactoryControlBar.Selected;
        if(selected==FactoryControlBar.Equipment.Oxidation||selected==FactoryControlBar.Equipment.Ellipsometer||selected==FactoryControlBar.Equipment.Implanter)
        {if(GUI.Button(new Rect(Screen.width/scale-220,18,200,36),"Jetson 원인·보정안 보기",new GUIStyle(GUI.skin.button){font=font,fontSize=17}))Open();}
        if(WindowOpen)
        {
            var color=GUI.color;var content=GUI.contentColor;var back=GUI.backgroundColor;
            GUI.color=GUI.contentColor=GUI.backgroundColor=Color.white;
            window.x=Mathf.Clamp(window.x,0,Mathf.Max(0,Screen.width/scale-window.width));window.y=Mathf.Clamp(window.y,0,Mathf.Max(0,Screen.height/scale-window.height));
            EnsureClassicStyles();
            window=GUI.Window(714844,window,DrawClassic,"",classicWindow);
            if(classicResizePending)
            {
                classicResizePending=false;
                if(!classicMaximized){classicRestoreWindow=window;window=new Rect(8,8,Mathf.Max(1020,Screen.width/scale-16),Mathf.Max(688,Screen.height/scale-16));}
                else window=classicRestoreWindow;
                classicMaximized=!classicMaximized;
            }
            GUI.color=color;GUI.contentColor=content;GUI.backgroundColor=back;
        }
        DrawGatewayWindow();
        GUI.matrix=matrix;GUI.depth=depth;
    }
    void OnDestroy(){if(Instance==this)Instance=null;DestroyClassicTextures();}
}
