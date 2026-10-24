using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

// The paired demo is explicit: a thickness verdict alone never supplies electrical measurements.
public class LotProcessAnalysis : MonoBehaviour
{
    public enum Status {Measuring,Pass,WaitingData,Queued,Running,Complete,Failed}
    public enum Equipment {Ellipsometer,Oxidation,Implanter}
    [Serializable] class ElectricalSamples {public string baseline_version;public ProcessAnalysisView.Sample[] cases;}
    [Serializable] public class Scenario
    {
        public string scenario_id,baseline_version,provenance;
        public float target_nm,lower_nm,upper_nm,oxide_ratio;
        public float[] readings_nm;
        public int n_wafers;
        public bool has_bv;
        public ProcessAnalysisView.Measurement measurement;
    }
    public class Record
    {
        public string lotId,inspectionId,requestId,scenarioId,detail;
        public float target,lower,upper;
        public float[] readings;
        public Status status;
        public bool evaluated,superseded,gatewayManaged;
        public int attempts;
        public ProcessAnalysisView.Payload result;
        public ProcessAnalysisView.Input electrical;
        public bool hasBv;
        public ElectricalSpec.Verdict electricalVerdict=ElectricalSpec.Verdict.Pending;
        public EllipsometerCycle.ElectricalDemo electricalDemo;
        public JetsonTestDataProtocol.Selection csv;
        public GatewayInspectionSnapshot inspectionSnapshot;
        public GatewayLotConditions.Condition tcadCondition;
        public string tcadExportPath,tcadExportError;
        public string tcadGatewayState;
        internal EllipsometerCycle source;
    }
    public static LotProcessAnalysis Instance {get;private set;}
    public IReadOnlyList<Record> Records=>records;
    public int RequestsSent {get;private set;}
    public Scenario PairedScenario {get;private set;}
    readonly List<Record> records=new List<Record>();
    ProcessAnalysisView view;
    ElectricalSamples electricalSamples;
    bool monitorOpen;
    Equipment monitorEquipment;
    string monitorLot;
    Rect monitorRect=new Rect(12,72,505,465);
    Font font;
    Texture2D background;
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]static void ResetStatic(){Instance=null;}
    void Awake()
    {
        Instance=this;view=GetComponent<ProcessAnalysisView>();
        var asset=Resources.Load<TextAsset>("FilmAnomalyScenario");if(asset)PairedScenario=JsonUtility.FromJson<Scenario>(asset.text);
        var samples=Resources.Load<TextAsset>("ProcessAnalysisSamples");if(samples)electricalSamples=JsonUtility.FromJson<ElectricalSamples>(samples.text);
        view.ResultReceived+=Receive;view.RequestFailed+=Fail;
    }
    public Record Latest(string lotId)=>records.FindLast(r=>r.lotId==lotId);
    public Record ForInspection(string inspection)=>records.Find(r=>r.inspectionId==inspection);
    static bool ThicknessKnown(Record r)=>r?.readings!=null&&r.readings.Length==3&&FilmInspectionRecipe.Finite(r.lower)&&FilmInspectionRecipe.Finite(r.upper)&&r.lower>0&&r.upper>=r.lower&&Array.TrueForAll(r.readings,FilmInspectionRecipe.Finite);
    public static bool ThicknessOk(Record r)=>ThicknessKnown(r)&&Array.TrueForAll(r.readings,x=>x>=r.lower&&x<=r.upper);
    public static bool IsNormal(Record r)=>r!=null&&r.evaluated&&ThicknessOk(r)&&r.electricalVerdict==ElectricalSpec.Verdict.OK;
    public static bool NeedsDiagnosis(Record r)=>r!=null&&r.evaluated&&(r.electricalVerdict==ElectricalSpec.Verdict.NG||ThicknessKnown(r)&&!ThicknessOk(r));

    public Record Begin(EllipsometerCycle source)
    {
        var same=records.Find(r=>r.lotId==source.lotId&&r.inspectionId==source.InspectionId);if(same!=null)return same;
        var previous=Latest(source.lotId);if(previous!=null)previous.superseded=true;
        // shortcut: keep at most 64 inspection snapshots during one Play session; durable audit is separate.
        if(records.Count>=64){var old=records.Find(r=>view.PendingRequestId==null||r.requestId!=view.PendingRequestId);if(old!=null)records.Remove(old);}
        var record=new Record{lotId=source.lotId,inspectionId=source.InspectionId,source=source,csv=source.InspectionCsv,electricalDemo=source.electricalDemo,status=Status.Measuring,detail="측정 대기 / 진행 중"};
        try{record.tcadCondition=GatewayLotConditions.ForLot(record.lotId);}catch(ArgumentException error){record.tcadExportError=error.Message;}
        records.Add(record);return record;
    }
    public void Inspected(EllipsometerCycle source)
    {
        var r=Begin(source);if(r.evaluated)return;
        r.evaluated=true;r.readings=(float[])source.readings.Clone();r.target=source.recipe.targetNm;r.lower=source.recipe.lowerNm;r.upper=source.recipe.upperNm;
        if(r.csv!=null)
        {
            var m=r.csv.Measurement;r.scenarioId=r.csv.Label;
            var input=ProcessAnalysisView.NewInput(r.lotId,PairedScenario?.baseline_version,r.csv.n_wafers,new ProcessAnalysisView.Measurement{vth=m.vth,gm=m.gm,id4v=m.id4v,bv=m.bv});
            if(ReceiveElectrical(source,r.inspectionId,input,true)){r.detail=r.csv.Label+" · "+r.detail;Refresh(r);return;}
            source.lotHeld=true;source.lotStatus="HOLD";r.status=Status.WaitingData;r.detail="CSV 입력 연결 실패 · 모델 기준/검사 상태 확인 필요";Refresh(r);return;
        }
        if(r.electricalDemo!=EllipsometerCycle.ElectricalDemo.ThicknessOnly)
        {
            bool normal=r.electricalDemo==EllipsometerCycle.ElectricalDemo.Normal;
            string name=normal?"normal":"oxide_plus15";
            var sample=electricalSamples?.cases==null?null:Array.Find(electricalSamples.cases,s=>s.name==name);
            var expected=normal?new[]{r.target*.996f,r.target*1.001f,r.target*1.003f}:new[]{r.target*1.146f,r.target*1.151f,r.target*1.153f};
            bool match=sample?.measurement!=null&&Near(r.lower,r.target*.95f)&&Near(r.upper,r.target*1.05f)&&r.readings.Length==3;
            if(match)for(int i=0;i<3;i++)match&=Near(r.readings[i],expected[i]);
            r.scenarioId=name;
            if(match&&ReceiveElectrical(source,r.inspectionId,ProcessAnalysisView.NewInput(r.lotId,electricalSamples.baseline_version,sample.n_wafers,sample.measurement),sample.has_bv))return;
            source.lotHeld=true;source.lotStatus="HOLD";r.status=Status.WaitingData;r.detail="HOLD · 시나리오/측정/모델 기준 불일치 · 분석 데이터 확인 필요";view.OpenLot(r.lotId);Refresh(r);return;
        }
        if(source.verdict!="FAIL"){r.status=Status.Pass;r.detail=source.lotHeld?"재측정 PASS · 검토 전 HOLD 유지":"PASS · 자동 분석 요청 없음";Refresh(r);return;}
        r.status=Matches(source,r)?Status.Queued:Status.WaitingData;
        r.detail=r.status==Status.Queued?"HOLD · 합성 전기특성 준비됨 · Jetson 연결/분석 순서 대기":"HOLD · 짝지어진 전기특성 없음 · 분석 데이터 대기";
        r.scenarioId=r.status==Status.Queued?PairedScenario.scenario_id:null;
        if(r.status==Status.Queued)
        {
            r.electrical=ProcessAnalysisView.NewInput(r.lotId,PairedScenario.baseline_version,PairedScenario.n_wafers,PairedScenario.measurement);
            r.hasBv=PairedScenario.has_bv;
            r.electricalVerdict=ElectricalSpec.Evaluate(r.electrical.measurement.vth,r.hasBv?(float?)r.electrical.measurement.bv:null);
        }
        FreezeTcadInspection(r);view.OpenLot(r.lotId);Refresh(r);
    }
    // Bind only to the exact completed inspection; late/different-LOT data cannot change the current LOT.
    public bool ReceiveElectrical(EllipsometerCycle source,string inspectionId,ProcessAnalysisView.Input input,bool hasBv)
    {
        var r=source?Latest(source.lotId):null;
        if(r==null||r.source!=source||r.inspectionId!=inspectionId||r.superseded||!r.evaluated||input?.measurement==null||input.lot_id!=r.lotId||input.data_source!="synthetic"||input.baseline_version!=PairedScenario?.baseline_version||r.attempts>0)return false;
        r.electrical=UnityEngine.JsonUtility.FromJson<ProcessAnalysisView.Input>(UnityEngine.JsonUtility.ToJson(input));r.hasBv=hasBv;
        r.electricalVerdict=ElectricalSpec.Evaluate(input.measurement.vth,hasBv?(float?)input.measurement.bv:null);
        bool hold=r.electricalVerdict!=ElectricalSpec.Verdict.OK||source.verdict=="FAIL";
        if(hold){source.lotHeld=true;source.lotStatus="HOLD";}
        r.status=r.electricalVerdict==ElectricalSpec.Verdict.Pending?Status.WaitingData:NeedsDiagnosis(r)?Status.Queued:Status.Pass;
        r.detail=r.status==Status.Queued?"HOLD · 전기특성/두께 이상 · Jetson 분석 대기":r.status==Status.WaitingData?"HOLD · 전기특성 전체 판정 대기":source.lotHeld?"전기특성 OK · 기존 HOLD는 검토 전 유지":"두께 PASS / 전기특성 OK · 정상 완료 / 보정 불필요";
        if(!hold&&r.status==Status.Queued)r.detail="두께 PASS / 전기특성 OK · Jetson 진단 확인 대기";
        FreezeTcadInspection(r);if(hold)view.OpenLot(r.lotId);Refresh(r);return true;
    }
    static void FreezeTcadInspection(Record r)
    {
        try{r.inspectionSnapshot=GatewayInspectionSnapshot.Capture(r.source,r);}
        catch(ArgumentException error){r.tcadExportError=error.Message;}
    }
    public bool BlocksRelease(string lotId)
    {var r=records.FindLast(x=>x.lotId==lotId&&x.electrical!=null);return r!=null&&r.electricalVerdict!=ElectricalSpec.Verdict.OK;}
    public static string ElectricalSummary(Record r)
    {return r?.electrical?.measurement==null?"전기특성 판정 대기 · 검사에 연결된 값 없음":ElectricalSpec.Describe(r.electrical.measurement.vth,r.hasBv?(float?)r.electrical.measurement.bv:null);}
    bool Matches(EllipsometerCycle source,Record r)
    {
        var s=PairedScenario;
        if(s==null||!source.demoHold||source.demoLow||s.measurement==null||s.readings_nm==null||s.readings_nm.Length!=3)return false;
        if(!Near(r.target,s.target_nm)||!Near(r.lower,s.lower_nm)||!Near(r.upper,s.upper_nm))return false;
        for(int i=0;i<3;i++)if(!Near(r.readings[i],s.readings_nm[i]))return false;
        return true;
    }
    static bool Near(float a,float b)=>FilmInspectionRecipe.Finite(a)&&FilmInspectionRecipe.Finite(b)&&Mathf.Abs(a-b)<.0005f;
    void Update()
    {
        if(!view.CanRequest)return;
        // Gateway predicts electrical outputs; this queue diagnoses the frozen CSV measurements separately.
        var next=records.Find(r=>!r.gatewayManaged&&!r.superseded&&r.status==Status.Queued&&NeedsDiagnosis(r));
        if(next!=null)_=Dispatch(next);
    }
    async Task Dispatch(Record r)
    {
        if(!NeedsDiagnosis(r))return;
        r.status=Status.Running;r.detail=(r.source&&r.source.lotHeld?"HOLD · ":"")+"Jetson 새 진단 계산 중";
        var input=r.electrical;
        r.requestId=input.request_id;r.attempts++;RequestsSent++;Refresh(r);
        bool sent=await view.RequestInput(input,r.hasBv);
        if(!sent&&r.status==Status.Running){r.status=Status.Failed;r.detail="HOLD · 분석 요청 실패 · 연결/로그 확인 필요";Refresh(r);}
    }
    void Receive(ProcessAnalysisView.Payload p)
    {
        var r=records.Find(x=>x.requestId==p.request_id&&x.lotId==p.lot_id);
        if(r==null||!NeedsDiagnosis(r))return;
        r.result=p;r.status=Status.Complete;
        r.detail=(r.source&&r.source.lotHeld?"HOLD · ":"")+(p.decided?"원인 후보: "+p.top_cause:"구분 불가 · 추가 측정 필요");
        SendTcadToGateway(r);view.OpenLot(r.lotId);view.SetAnalysisTab(1);Refresh(r);
    }
    public bool SendTcadToGateway(Record r)
    {
        try
        {
            if(!NeedsDiagnosis(r))throw new ArgumentException("정상 검사 또는 판정 대기 · 보정 후보 전송 대상 아님");
            var bridge=GatewayInspectionBridge.Instance;
            if(!bridge)throw new ArgumentException("Gateway DB 결과 창에서 요청 토큰을 입력하고 자동 검사 연동을 시작하세요.");
            var job=bridge.QueueTcadCandidate(r);r.tcadGatewayState=job.state;return true;
        }
        catch(Exception error) when(error is ArgumentException||error is System.IO.IOException||error is UnauthorizedAccessException)
        {if(r!=null)r.tcadGatewayState="DB 미전송 · "+error.Message;return false;}
    }
    public bool ExportTcad(Record r)
    {
        try
        {
            var job=GatewayInspectionBridge.Instance?.Jobs;
            GatewayInspectionBridge.Job linked=null;
            if(job!=null)foreach(var item in job)if(item.inspectionId==r.inspectionId)linked=item;
            r.tcadExportPath=TcadVerificationPackage.Save(r,r.result,linked);r.tcadExportError=null;return true;
        }
        catch(Exception error) when(error is ArgumentException||error is System.IO.IOException||error is UnauthorizedAccessException)
        {r.tcadExportError=error.Message;return false;}
    }
    void Fail(string requestId,string reason)
    {
        var r=records.Find(x=>x.requestId==requestId);if(r==null)return;
        r.status=Status.Failed;r.detail="HOLD · "+reason;Refresh(r);
    }
    static void Refresh(Record r){if(r.source&&r.source.InspectionId==r.inspectionId&&r.source.dashboard)r.source.dashboard.Refresh();}
    public static string Summary(Equipment equipment,string lotId)
    {
        var r=Instance?Instance.Latest(lotId):null;
        if(r==null)return lotId+" | 해당 LOT 분석 없음";
        if(r.result==null)return lotId+" | "+r.detail;
        string change=equipment==Equipment.Ellipsometer?(r.result.decided?"원인 후보: "+r.result.top_cause:"구분 불가 · 추가 확인"):
            equipment==Equipment.Oxidation?"산화막 제안 ×"+r.result.oxide_factor.ToString("F3"):Mathf.Abs(r.result.dose_factor-1)<.0001f?"도즈 변경 제안 없음":"도즈 제안 ×"+r.result.dose_factor.ToString("F3");
        return lotId+" | "+change+" | 합성 · TCAD 미검증 / 미적용";
    }
    public void OpenMonitor(Equipment equipment,string lotId){monitorEquipment=equipment;monitorLot=lotId;monitorOpen=true;}
    GUIStyle Label(int size)=>new GUIStyle(GUI.skin.label){font=font,fontSize=size,wordWrap=true,normal={textColor=new Color32(226,236,247,255)}};
    void DrawMonitor(int id)
    {
        if(GUI.Button(new Rect(462,3,32,25),"X"))monitorOpen=false;
        var r=Latest(monitorLot);GUI.Label(new Rect(18,34,465,32),"LOT: "+monitorLot,Label(22));
        GUI.Label(new Rect(18,76,465,60),r?.detail??"해당 LOT의 공정 분석 없음",Label(20));
        if(r!=null&&r.readings!=null)GUI.Label(new Rect(18,143,465,46),$"두께 {(Array.TrueForAll(r.readings,x=>x>=r.lower&&x<=r.upper)?"PASS":"FAIL")} · {r.readings[0]:F1} / {r.readings[1]:F1} / {r.readings[2]:F1} nm\n허용 {r.lower:F1}–{r.upper:F1} nm · 합성 시나리오",Label(16));
        var p=r?.result;
        string correction=monitorEquipment==Equipment.Ellipsometer?"계측 결과와 분석 상태 표시 · 레시피 변경 대상 아님":p==null?"보정 제안 수신 대기":monitorEquipment==Equipment.Oxidation?"산화막 보정 제안 ×"+p.oxide_factor.ToString("F3"):Mathf.Abs(p.dose_factor-1)<.0001f?"도즈 변경 제안 없음":"도즈 보정 제안 ×"+p.dose_factor.ToString("F3");
        GUI.Label(new Rect(18,209,465,58),correction,Label(23));
        GUI.Label(new Rect(18,277,465,64),ElectricalSummary(r),Label(15));
        if(GUI.Button(new Rect(18,350,465,34),"이 LOT의 전체 원인·보정안"))view.OpenLot(monitorLot);
        GUI.Label(new Rect(18,397,465,48),r!=null&&r.status!=Status.Pass&&r.status!=Status.Measuring?"TCAD 재검증과 엔지니어 승인 전까지\n현재 LOT 보류 · 다음 LOT 레시피 변경 없음":"분석은 레시피를 변경하지 않습니다.\n보정 적용은 검증·승인 연결 후 가능합니다.",Label(17));
        GUI.DragWindow(new Rect(0,0,455,28));
    }
    void OnGUI()
    {
        if(!Application.isPlaying)return;
        if(!font)font=Font.CreateDynamicFontFromOSFont(new[]{"Malgun Gothic","Arial"},18);
        var matrix=GUI.matrix;int depth=GUI.depth;GUI.depth=-40;float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);GUI.matrix=Matrix4x4.Scale(Vector3.one*scale);
        var selected=FactoryControlBar.Selected;string lot=null;Equipment role=Equipment.Ellipsometer;
        if(selected==FactoryControlBar.Equipment.Ellipsometer){var c=FindAnyObjectByType<EllipsometerCycle>();if(c)lot=c.lotId;}
        if(selected==FactoryControlBar.Equipment.Oxidation){var c=FindAnyObjectByType<IntegratedOxidationCycle>();if(c)lot=c.lotId;role=Equipment.Oxidation;}
        if(selected==FactoryControlBar.Equipment.Implanter){var c=FindAnyObjectByType<IonImplantCycle>();if(c)lot=c.incomingLotId;role=Equipment.Implanter;}
        if(lot!=null&&GUI.Button(new Rect(Screen.width/scale-220,61,200,34),"설비 모니터 · 이 LOT",new GUIStyle(GUI.skin.button){font=font,fontSize=17}))OpenMonitor(role,lot);
        if(monitorOpen)
        {
            if(!background){background=new Texture2D(1,1);background.SetPixel(0,0,new Color32(12,24,38,255));background.Apply();}
            var style=new GUIStyle(GUI.skin.window){font=font,fontSize=19};style.normal.background=style.onNormal.background=background;style.normal.textColor=Color.white;
            monitorRect.x=Mathf.Clamp(monitorRect.x,0,Mathf.Max(0,Screen.width/scale-monitorRect.width));monitorRect.y=Mathf.Clamp(monitorRect.y,0,Mathf.Max(0,Screen.height/scale-monitorRect.height));
            string name=monitorEquipment==Equipment.Oxidation?"산화로":monitorEquipment==Equipment.Implanter?"이온주입기":"엘립소미터";
            monitorRect=GUI.Window(714850,monitorRect,DrawMonitor,name+" 설비 모니터 · LOT 분석",style);
        }
        GUI.matrix=matrix;GUI.depth=depth;
    }
    void OnDestroy(){if(view){view.ResultReceived-=Receive;view.RequestFailed-=Fail;}if(Instance==this)Instance=null;if(background)Destroy(background);}
}
