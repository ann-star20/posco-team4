using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

// One inspected product per packet. Image and verdict travel together, never as unrelated streams.
public class AoiJetsonFeed : MonoBehaviour
{
    [Serializable] public class Packet
    {
        public string result_id,product_id,frame_id,label,jpeg_base64,data_source;
        public string direct_verdict,request_id,lot_id,inspected_at,persistence_status;
        public AoiDirectProtocol.Detection[] defects,parts;
        public float confidence;
        public long captured_at_ms;
    }
    public string resultUrl="http://192.168.213.167:8080/aoi/latest";
    public float minimumConfidence=.8f,maxAgeSeconds=5,pollSeconds=.5f;
    public AoiCycleDemo sorter;
    public AoiDashboard dashboard;
    public bool demoMode;
    public bool useWebSocket;
    [NonSerialized] public bool directMode;
    [NonSerialized] public bool transportReady;
    [NonSerialized] public Packet current;
    [NonSerialized] public Texture2D frame;
    [NonSerialized] public string connection="연결 대기",notice="젯슨 영상·인식 서비스 대기";
    public bool Busy{get;private set;}
    public bool InspectionCycleRunning{get;private set;}
    public bool SortCompleted=>current!=null&&completedResultId==current.result_id;
    public bool DisplayCurrent=>current!=null&&(Fresh||Busy||SortCompleted||!string.IsNullOrEmpty(current.direct_verdict));
    public string Verdict=>current==null?"대기":!DisplayCurrent?"만료":!string.IsNullOrEmpty(current.direct_verdict)?current.direct_verdict:current.confidence<minimumConfidence?"검토":current.label=="normal"?"OK":"NG";
    public bool Fresh=>current!=null&&(demoMode||ResultAge<=maxAgeSeconds&&ResultAge>=-2);
    public bool CanSort=>string.IsNullOrEmpty(SortBlockReason);
    public string SortBlockReason
    {
        get
        {
            if(Busy)return "분류 동작 중";
            if(InspectionCycleRunning)return "AOI 검사 위치·결과 대기";
            if(useWebSocket&&!demoMode&&!transportReady)return "Jetson 연결·결과 확인 필요";
            if(current==null)return "검사 결과 없음";
            if(!Fresh)return "결과 유효시간 초과 · 재검사 필요";
            if(float.IsNaN(current.confidence)||current.confidence<minimumConfidence)return "모델 점수 기준 미달";
            if(current.label!="normal"&&current.label!="crash"&&current.label!="band"&&current.label!="scratch"&&current.label!="bend")return "미등록 검출 항목";
            if(Verdict!="OK"&&Verdict!="NG")return "판정 보류 · 추가 확인 필요";
            if(seen.Contains(current.result_id))return "이미 분류한 검사 결과";
            return "";
        }
    }
    Packet directReceivedPacket;
    double directReceivedAt;
    // Correlated direct replies use a local monotonic receipt clock, not the Jetson wall clock.
    double ResultAge=>ReferenceEquals(current,directReceivedPacket)?Time.realtimeSinceStartupAsDouble-directReceivedAt:current==null?double.PositiveInfinity:Age(current);
    readonly HashSet<string> seen=new HashSet<string>();
    readonly Queue<string> order=new Queue<string>();
    UnityWebRequest request;
    bool wasFresh;
    Coroutine sortRoutine;
    Coroutine inspectionRoutine;
    bool inspectionResolved;
    string completedResultId;
    public static long Now=>DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    static double Age(Packet p)=>(Now-p.captured_at_ms)/1000.0;
    public static void Validate(Packet p,float maxAge,bool requireImage=true)
    {
        if(p==null||string.IsNullOrWhiteSpace(p.result_id)||p.result_id.Length>100||string.IsNullOrWhiteSpace(p.product_id)||p.product_id.Length>100)throw new ArgumentException("제품·결과 ID 누락");
        if(p.label!="normal"&&p.label!="crash"&&p.label!="band"&&p.label!="scratch")throw new ArgumentException("미등록 불량 유형");
        if(float.IsNaN(p.confidence)||float.IsInfinity(p.confidence)||p.confidence<0||p.confidence>1)throw new ArgumentException("신뢰도 범위 오류");
        if(Age(p)>maxAge||Age(p)<-2)throw new ArgumentException("검사 시각 만료·시계 확인 필요");
        if(requireImage&&string.IsNullOrEmpty(p.jpeg_base64)||p.jpeg_base64!=null&&p.jpeg_base64.Length>2800000)throw new ArgumentException("검사 이미지 누락·크기 초과");
    }
    void Start(){if(!GetComponent<AoiDirectClient>())gameObject.AddComponent<AoiDirectClient>();StartCoroutine(Poll());}
    IEnumerator Poll()
    {
        while(true)
        {
            if(!useWebSocket&&!demoMode&&!Busy&&!CanSort&&!string.IsNullOrWhiteSpace(resultUrl))
            {
                request=UnityWebRequest.Get(resultUrl);request.timeout=3;
                var operation=request.SendWebRequest();
                while(!operation.isDone){if(request.downloadedBytes>4000000)request.Abort();yield return null;}
                if(!useWebSocket&&!demoMode&&!Busy)
                {
                    if(request.result!=UnityWebRequest.Result.Success)Clear("젯슨 연결 대기","영상·결과 수신 안 됨 · 분류 정지");
                    else if(request.responseCode==204)Clear("젯슨 연결됨","검사 결과 대기 · 분류 정지");
                    else
                    {
                        try{AcceptJson(request.downloadHandler.text);}catch(Exception e){Clear("수신 오류",e.Message+" · 분류 정지");}
                    }
                }
                request.Dispose();request=null;
            }
            yield return new WaitForSecondsRealtime(Mathf.Max(.2f,pollSeconds));
        }
    }
    public bool AcceptJson(string json)
    {
        if(Busy)return false;
        if(json.Length>4000000)throw new ArgumentException("결과 크기 초과");
        return AcceptPacket(JsonUtility.FromJson<Packet>(json));
    }
    public bool AcceptPacket(Packet p,bool requireImage=true)
    {
        if(Busy||demoMode&&useWebSocket)return false;
        Validate(p,maxAgeSeconds,requireImage);
        if(seen.Contains(p.result_id)){connection=useWebSocket?"서버 연결됨":"젯슨 연결됨";return false;}
        if(useWebSocket&&CanSort&&current.result_id!=p.result_id){notice="기존 제품의 분류 대기 중 · 새 결과는 재전송 필요";Refresh();return false;}
        if(current!=null&&p.captured_at_ms<current.captured_at_ms)return false;
        if(current!=null&&current.result_id==p.result_id)return false;
        Texture2D image=null;
        if(!string.IsNullOrEmpty(p.jpeg_base64))
        {
            var data=Convert.FromBase64String(p.jpeg_base64);image=new Texture2D(2,2,TextureFormat.RGB24,false);
            if(!ImageConversion.LoadImage(image,data)||image.width>1920||image.height>1080){Destroy(image);throw new ArgumentException("JPEG 디코드 실패·1920×1080 초과");}
        }
        ReplaceFrame(image);current=p;completedResultId=null;connection=useWebSocket?"서버 연결됨":"젯슨 연결됨";notice=p.confidence<minimumConfidence?"신뢰도 부족 · 재검토 필요 · 자동 분류 안 함":(p.data_source=="demo"?"시험 결과 수신 · ":"검사 결과 수신 · ")+"분류 시작 대기";AoiInspectionHistory.Instance.Record(this);Refresh();return true;
    }
    public void AcceptDirect(AoiDirectProtocol.Reply reply,byte[] photo)
    {
        if(Busy||demoMode)throw new InvalidOperationException("검사 결과를 받을 수 없는 상태");
        var image=new Texture2D(2,2,TextureFormat.RGB24,false);
        if(!ImageConversion.LoadImage(image,photo)||image.width!=reply.image.width||image.height!=reply.image.height)
        {Destroy(image);throw new ArgumentException("검사 JPEG 디코드·크기 불일치");}
        ReplaceFrame(image);
        current=new Packet{result_id=reply.message_id,product_id=reply.unit_id,frame_id=reply.image.image_id,label=AoiDirectProtocol.Label(reply),confidence=AoiDirectProtocol.Confidence(reply),captured_at_ms=DateTimeOffset.Parse(reply.occurred_at).ToUnixTimeMilliseconds(),direct_verdict=reply.verdict=="pass"?"OK":reply.verdict=="review"?"검토":"NG",data_source=reply.result_origin,request_id=reply.request_id,lot_id=reply.lot_id,inspected_at=reply.occurred_at,defects=reply.defects,parts=reply.parts};
        directReceivedPacket=current;directReceivedAt=Time.realtimeSinceStartupAsDouble;
        current.persistence_status=reply.persistence_status;
        completedResultId=null;transportReady=true;connection="Jetson 직접 검사 · 결과 수신";
        notice=(reply.result_origin=="mock"?"시험용 mock · ":"출처: "+reply.result_origin+" · ")+"결과 사진 · 실시간 영상 아님";AoiInspectionHistory.Instance.Record(this);Refresh();
    }
    public void SetTransportState(bool ready,string state,string reason)
    {
        transportReady=ready;if(demoMode)return;
        if(!ready&&InspectionCycleRunning)ResolveInspectionCycle(false);
        if(!ready&&Busy)
        {if(sortRoutine!=null)StopCoroutine(sortRoutine);sortRoutine=null;if(inspectionRoutine!=null)StopCoroutine(inspectionRoutine);inspectionRoutine=null;Busy=false;sorter.AbortExternalSort();}
        if(!ready)Clear(state,reason);else{connection=state;notice=reason;Refresh();}
    }
    public void Clear(string state,string reason)
    {if(Busy)return;current=null;completedResultId=null;ReplaceFrame(null);connection=state;notice=reason;Refresh();}
    void ReplaceFrame(Texture2D image){directReceivedPacket=null;if(frame)Destroy(frame);frame=image;}
    public void SetMode(bool demo)
        {if(Busy||InspectionCycleRunning)return;if(demoMode!=demo)sorter.okCount=sorter.ngCount=0;demoMode=demo;if(request!=null)request.Abort();Clear(demo?"DEMO · 실측 아님":useWebSocket&&transportReady?"서버 연결됨":"연결 대기",demo?"데모 예시 선택":"검사 결과 수신 대기");}
    public void Demo(string label)
    {
        if(!demoMode||Busy)return;
        var image=new Texture2D(320,240,TextureFormat.RGB24,false);var pixels=new Color32[320*240];
        for(int y=0;y<240;y++)for(int x=0;x<320;x++)
        {bool body=x>105&&x<215&&y>70&&y<180;bool leads=y>30&&y<70&&((x>113&&x<125)||(x>153&&x<165)||(x>193&&x<205));pixels[y*320+x]=body?new Color32(48,57,68,255):leads?new Color32(180,194,205,255):new Color32(22,34,46,255);}
        image.SetPixels32(pixels);image.Apply();ReplaceFrame(image);
        current=new Packet{result_id="DEMO-"+Guid.NewGuid().ToString("N"),product_id="DEMO-013",label=label,confidence=.987f,captured_at_ms=Now,data_source="demo",defects=label=="normal"?new AoiDirectProtocol.Detection[0]:new[]{new AoiDirectProtocol.Detection{class_name=label,confidence=.987f,bbox_xyxy=new[]{125f,80f,195f,145f}}}};completedResultId=null;
        connection="DEMO · 실제 카메라 아님";notice="예시 판정 · 제품 도식 · 분류 시작 대기";AoiInspectionHistory.Instance.Record(this);Refresh();
    }
    public void BeginSort(){if(CanSort)sortRoutine=StartCoroutine(Sort());}
    public bool BeginInspectionCycle()
    {
        if(!sorter||Busy||InspectionCycleRunning||sorter.Running)return false;
        InspectionCycleRunning=true;inspectionResolved=false;inspectionRoutine=StartCoroutine(AutomaticInspection());return true;
    }
    public void ResolveInspectionCycle(bool completed)
    {
        if(!InspectionCycleRunning)return;
        if(completed){inspectionResolved=true;return;}
        if(inspectionRoutine!=null)StopCoroutine(inspectionRoutine);inspectionRoutine=null;InspectionCycleRunning=false;inspectionResolved=false;
        sorter.AbortExternalSort("HOLD / INSPECTION FAILED");Refresh();
    }
    IEnumerator AutomaticInspection()
    {
        yield return sorter.PrepareInspection();
        while(!inspectionResolved)yield return null;
        InspectionCycleRunning=false;
        if(!CanSort){sorter.AbortExternalSort("HOLD / RESULT CHECK REQUIRED");notice="자동 분류 보류 · "+SortBlockReason;inspectionRoutine=null;Refresh();yield break;}
        sortRoutine=StartCoroutine(Sort(true));yield return sortRoutine;inspectionRoutine=null;
    }
    IEnumerator Sort(bool prepared=false)
    {
        var accepted=current;bool ng=Verdict=="NG";Busy=true;seen.Add(accepted.result_id);order.Enqueue(accepted.result_id);
        while(order.Count>256)seen.Remove(order.Dequeue());
        notice=(ng?"NG":"OK")+" 박스로 분류 중 · "+accepted.product_id;Refresh();
        if(prepared)yield return sorter.SortPrepared(ng);else yield return sorter.SortOne(ng);
        completedResultId=accepted.result_id;Busy=false;sortRoutine=null;notice=(ng?"NG":"OK")+" 박스 도착 · "+accepted.product_id+" · 마지막 검사 결과 · 재분류 차단";Refresh();
    }
    void Update(){if(wasFresh!=Fresh){wasFresh=Fresh;Refresh();}}
    void Refresh(){if(dashboard)dashboard.Refresh();}
    void OnDisable(){if(request!=null)request.Abort();ResolveInspectionCycle(false);if(inspectionRoutine!=null){StopCoroutine(inspectionRoutine);inspectionRoutine=null;}if(sortRoutine!=null){StopCoroutine(sortRoutine);sortRoutine=null;Busy=false;if(sorter)sorter.AbortExternalSort();}}
    void OnDestroy(){if(frame)Destroy(frame);}
}
