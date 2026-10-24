using System;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

// One request per connection. The token lives only in this Play session.
public class AoiDirectClient : MonoBehaviour
{
    public const string Endpoint="ws://192.168.213.167:8400/aoi";
    public AoiJetsonFeed feed;
    public bool Inspecting { get; private set; }
    public string Status { get; private set; }="카메라 연결·검사 토큰 입력 후 현재 화면 검사";
    string token="";
    CancellationTokenSource lifetime;
    ClientWebSocket activeSocket;
    public string SessionToken { set { if(!Inspecting)token=(value??"").Trim(); } }
    public bool HasToken=>!string.IsNullOrWhiteSpace(token);
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Attach()
    {foreach(var source in FindObjectsByType<AoiJetsonFeed>())if(!source.GetComponent<AoiDirectClient>())source.gameObject.AddComponent<AoiDirectClient>();}
    void OnEnable()
    {
        feed=GetComponent<AoiJetsonFeed>();lifetime=new CancellationTokenSource();
        if(feed){feed.directMode=true;feed.useWebSocket=true;feed.SetTransportState(false,"Jetson 직접 검사 대기",Status);}
    }
    public void BeginCameraInspection(AoiCameraStream camera)
    {
        if(!camera||!camera.TryReferencedFrame(out var photo,out var cameraId,out var frameId)){Status="검사할 최신 Jetson 프레임 없음 · 8500 영상 연결을 확인하세요.";return;}
        BeginInspection(photo,cameraId,frameId,camera.InspectionEndpoint);
    }
    public async void BeginInspection(byte[] input=null,string cameraId=null,long frameId=-1,string endpoint=null)
    {
        if(!feed||Inspecting||feed.Busy||feed.InspectionCycleRunning||feed.demoMode||!HasToken||lifetime==null)return;
        Inspecting=true;float started=Time.realtimeSinceStartup;bool completed=false;
        var cancel=lifetime.Token;
        var request=new AoiDirectProtocol.Request{api_token=token};
        bool cameraRequest=!string.IsNullOrEmpty(cameraId);
        if(cameraRequest){request.camera_id=cameraId;request.frame_id=frameId;request.lot_id="LOT-001";request.unit_id="MOSFET-"+request.request_id.Substring(0,8);}
        feed.Clear("Jetson 연결 중",cameraRequest?"현재 카메라 화면 검사 요청 중 · 분류 정지":"시험 사진 검사 요청 중 · 분류 정지");feed.transportReady=false;
        Status="Jetson 연결 중";
        string failure="Jetson 접속 실패 · 서버 실행과 USB 연결 확인";
        try
        {
            failure="AOI 설비 동작 중 · 기존 동작 완료 후 다시 검사하세요.";
            if(!feed.BeginInspectionCycle())throw new InvalidOperationException();
            if(feed.dashboard)feed.dashboard.BeginScanPresentation(input);
            failure="Jetson 접속 실패 · 서버 실행과 USB 연결 확인";
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel))
            using(var socket=new ClientWebSocket())
            {
                activeSocket=socket;timeout.CancelAfter(TimeSpan.FromSeconds(60));socket.Options.Proxy=null;
                await socket.ConnectAsync(new Uri(endpoint??Endpoint),timeout.Token);
                failure="검사 프레임 번호 전송 실패";
                var bytes=Encoding.UTF8.GetBytes(cameraRequest?JsonUtility.ToJson(new AoiPreviewProtocol.FrameRequest(request)):JsonUtility.ToJson(request));request.api_token=null;
                try { await socket.SendAsync(new ArraySegment<byte>(bytes),WebSocketMessageType.Text,true,timeout.Token); }
                finally { Array.Clear(bytes,0,bytes.Length); }
                Status="요청 전송 완료 · 결과와 사진 수신 대기";feed.connection=Status;
                failure="Jetson 응답 수신 실패 · 서버 연결 또는 검사 시간 초과";
                AoiDirectProtocol.Reply reply=null;
                for(int i=0;i<16;i++)
                {
                    var raw=await Receive(socket,WebSocketMessageType.Text,1024*1024,timeout.Token);
                    reply=JsonUtility.FromJson<AoiDirectProtocol.Reply>(new UTF8Encoding(false,true).GetString(raw));
                    if(reply==null)throw new IOException("결과 JSON 오류");
                    if(reply.type=="aoi.inspection.accepted"&&!string.IsNullOrEmpty(reply.request_id)&&reply.request_id!=request.request_id)throw new IOException("Accepted request mismatch");
                    if(reply.type=="aoi.inspection.failed"){failure=AoiDirectProtocol.FailureReason(reply.error_code);throw new IOException();}
                    if(reply.type=="aoi.inspection.completed")break;
                    reply=null;
                }
                failure="Jetson 결과 형식·요청 ID·사진 출처 검증 실패";
                AoiDirectProtocol.ValidateReply(reply,request);
                Status="결과 수신 · JPEG 사진 수신 중";
                failure="결과는 수신됨 · 결과 사진 수신 또는 무결성 검사 실패";
                var photo=await Receive(socket,WebSocketMessageType.Binary,AoiDirectProtocol.MaxImageBytes,timeout.Token);
                AoiDirectProtocol.ValidatePhoto(reply.image,photo);
                // Keep the captured frame visible for the animation; publish only verified results.
                float remaining=AoiDashboard.ScanDuration-(Time.realtimeSinceStartup-started);
                if(remaining>0)await Task.Delay(Mathf.CeilToInt(remaining*1000),timeout.Token);
                cancel.ThrowIfCancellationRequested();
                if(feed.demoMode)throw new IOException("DEMO 모드 변경으로 직접 검사 결과 취소");
                failure="결과·사진 수신됨 · Unity 대시보드 반영 실패";
                feed.AcceptDirect(reply,photo);
                completed=true;
                Status=reply.result_origin=="mock"?"시험용 mock 결과·사진 수신 완료":"Jetson 결과·사진 수신 완료 · 출처: "+reply.result_origin;
            }
        }
        catch(Exception)
        {
            if(!cancel.IsCancellationRequested&&feed)
            {
                // Server text and exception messages may contain credentials; never display them.
                Status="검사 실패 · "+failure;
                feed.SetTransportState(false,"Jetson 검사 실패",Status);
            }
        }
        finally { request.api_token=null;if(input!=null)Array.Clear(input,0,input.Length);activeSocket=null;Inspecting=false;if(feed){if(feed.dashboard)feed.dashboard.EndScanPresentation(completed);feed.ResolveInspectionCycle(completed);} }
    }
    static async Task<byte[]> Receive(ClientWebSocket socket,WebSocketMessageType type,int limit,CancellationToken cancel)
    {
        var buffer=new byte[16384];
        using(var stream=new MemoryStream())
        {
            WebSocketReceiveResult part;
            do
            {
                part=await socket.ReceiveAsync(new ArraySegment<byte>(buffer),cancel).ConfigureAwait(false);
                if(part.MessageType!=type||stream.Length+part.Count>limit)throw new IOException("Unexpected or oversized AOI frame");
                stream.Write(buffer,0,part.Count);
            }while(!part.EndOfMessage);
            return stream.ToArray();
        }
    }
    void OnDisable()
    {
        token="";lifetime?.Cancel();activeSocket?.Abort();lifetime?.Dispose();lifetime=null;
        if(feed){feed.directMode=false;feed.SetTransportState(false,"직접 검사 종료","수신 정지 · 분류 대기");}
    }
}
