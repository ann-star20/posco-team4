using System;
using System.IO;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class AoiCameraStream : MonoBehaviour
{
    const string Preference="AOI.PhoneCamera.Address";
    readonly object gate=new object();
    CancellationTokenSource cancellation;
    byte[] pending;
    byte[] latestJpeg;
    AoiPreviewProtocol.Frame pendingMetadata,displayedMetadata;
    ClientWebSocket previewSocket;
    bool previewTextureLogged;
    public bool IsJetsonPreview{get;private set;}
    public string CameraId{get;private set;}="aoi-camera-1";
    public long FrameId=>Frame&&displayedMetadata!=null?displayedMetadata.frame_id:-1;
    public bool CanInspectFrame=>IsJetsonPreview&&Frame&&displayedMetadata!=null&&Time.realtimeSinceStartup-receivedAt<=1.5f;
    public string InspectionEndpoint=>AoiPreviewProtocol.InspectionAddress(Address);
    long sampledAt;
    string state="카메라 연결 대기 · 주소 입력";
    int generation;
    bool running;
    Texture2D image;
    float receivedAt=-100;
    public string Address {get;private set;}="";
    public string Status {get{lock(gate)return running&&image&&Time.realtimeSinceStartup-receivedAt>=3?"영상 지연 · 마지막 화면 숨김":state;}}
    public bool Running {get{lock(gate)return running;}}
    public Texture2D Frame=>Running&&Time.realtimeSinceStartup-receivedAt<3?image:null;
    void Awake()
    {
        string saved=PlayerPrefs.GetString("AOI.JetsonPreview.Address",AoiPreviewProtocol.DefaultAddress);
        Address=AoiPreviewProtocol.UpgradeSavedAddress(saved);
        if(Address!=saved){PlayerPrefs.SetString("AOI.JetsonPreview.Address",Address);PlayerPrefs.Save();}
        CameraId=PlayerPrefs.GetString("AOI.JetsonPreview.CameraId","aoi-camera-1");
    }
    public bool ConnectJetson(string input,string previewToken,string cameraId)
    {
        Uri uri;
        try{uri=AoiPreviewProtocol.Address(input);if(string.IsNullOrWhiteSpace(previewToken)||previewToken.Length>2048)throw new ArgumentException("영상용 CAMERA_PREVIEW_TOKEN을 입력하세요.");if(string.IsNullOrWhiteSpace(cameraId)||cameraId.Length>100)throw new ArgumentException("카메라 ID를 입력하세요.");}
        catch(ArgumentException e){lock(gate)state=e.Message;return false;}
        Disconnect();Address=uri.AbsoluteUri;CameraId=cameraId.Trim();IsJetsonPreview=true;
        PlayerPrefs.SetString("AOI.JetsonPreview.Address",Address);PlayerPrefs.SetString("AOI.JetsonPreview.CameraId",CameraId);PlayerPrefs.Save();
        var source=new CancellationTokenSource();cancellation=source;int session;lock(gate){session=++generation;running=true;state="Jetson 영상 구독 중";}
        previewTextureLogged=false;_=ReadPreview(uri,previewToken.Trim(),CameraId,source,session);return true;
    }
    async Task ReadPreview(Uri uri,string previewToken,string cameraId,CancellationTokenSource source,int session)
    {
        string error="Jetson 영상 연결 종료 · 다시 연결하세요.";
        string phase="WebSocket 연결 대기";
        try
        {
            using(var socket=new ClientWebSocket())
            {
                lock(gate){if(session!=generation)return;previewSocket=socket;}
                socket.Options.Proxy=null;source.CancelAfter(15000);await socket.ConnectAsync(uri,source.Token);
                Debug.Log("[AOI Preview] WS connected: "+uri.Host+":"+uri.Port);
                var subscription=new AoiPreviewProtocol.Subscription{api_token=previewToken,camera_id=cameraId};
                var bytes=Encoding.UTF8.GetBytes(JsonUtility.ToJson(subscription));subscription.api_token=null;previewToken=null;
                try{await socket.SendAsync(new ArraySegment<byte>(bytes),WebSocketMessageType.Text,true,source.Token);}finally{Array.Clear(bytes,0,bytes.Length);}
                phase="구독 승인 대기";source.CancelAfter(15000);
                var raw=await AoiPreviewProtocol.Receive(socket,WebSocketMessageType.Text,65536,source.Token);
                var ack=JsonUtility.FromJson<AoiPreviewProtocol.Frame>(new UTF8Encoding(false,true).GetString(raw));
                var rejection=AoiPreviewProtocol.SubscriptionFailure(ack,cameraId);
                if(rejection!=null){error=rejection;Debug.LogWarning("[AOI Preview] "+rejection);return;}
                Debug.Log("[AOI Preview] TEXT received: camera.preview.subscribed");
                long previous=-1;
                while(true)
                {
                    phase="프레임 JSON 대기";if(previous<0)lock(gate)if(session==generation)state="Jetson 구독 승인 · 프레임 JSON 대기";
                    source.CancelAfter(15000);raw=await AoiPreviewProtocol.Receive(socket,WebSocketMessageType.Text,65536,source.Token);
                    var metadata=JsonUtility.FromJson<AoiPreviewProtocol.Frame>(new UTF8Encoding(false,true).GetString(raw));AoiPreviewProtocol.ValidateFrame(metadata,cameraId,previous);
                    bool first=previous<0;
                    if(first)Debug.Log("[AOI Preview] TEXT received: camera.preview.frame frame_id="+metadata.frame_id+" byte_length="+metadata.byte_length);
                    phase="JPEG 수신 대기 (frame "+metadata.frame_id+")";source.CancelAfter(15000);
                    var jpeg=await AoiPreviewProtocol.Receive(socket,WebSocketMessageType.Binary,AoiCameraProtocol.MaxBytes,source.Token,first?(Action<string>)(message=>Debug.Log("[AOI Preview] "+message)):null);AoiPreviewProtocol.ValidatePhoto(metadata,jpeg);previous=metadata.frame_id;
                    lock(gate)if(session==generation){pending=jpeg;pendingMetadata=metadata;}
                }
            }
        }
        catch(OperationCanceledException){error="Jetson 영상 시간 초과 · "+phase;lock(gate)if(session==generation)Debug.LogWarning("[AOI Preview] Timeout: "+phase);}
        catch(Exception e){error="Jetson 영상 수신 실패 · "+phase;lock(gate)if(session==generation)Debug.LogWarning("[AOI Preview] Receive failed at "+phase+" ("+e.GetType().Name+")");}
        finally{previewToken=null;lock(gate)if(session==generation){running=false;pending=null;pendingMetadata=null;previewSocket=null;state=error;}source.Dispose();}
    }
    public bool Connect(string input,string user="",string password="")
    {
        Uri uri;HttpClientHandler handler;
        try{uri=AoiCameraProtocol.Address(input);handler=AoiCameraAuth.Create(uri,user,password);}catch(ArgumentException e){lock(gate)state=e.Message;return false;}
        Disconnect();Address=uri.AbsoluteUri;PlayerPrefs.SetString(Preference,Address);PlayerPrefs.Save();
        var source=new CancellationTokenSource();cancellation=source;
        int session;lock(gate){session=++generation;running=true;state="카메라 연결 중";}
        _=Task.Run(()=>Read(uri,handler,source,session));return true;
    }
    async Task Read(Uri uri,HttpClientHandler handler,CancellationTokenSource source,int session)
    {
        string error="영상 연결 종료 · 다시 연결하세요.";
        try
        {
            using(source)
            using(handler)
            using(var client=new HttpClient(handler){Timeout=Timeout.InfiniteTimeSpan})
            {
                source.CancelAfter(15000);
                using(var reply=await client.GetAsync(uri,HttpCompletionOption.ResponseHeadersRead,source.Token).ConfigureAwait(false))
                {
                    if(reply.StatusCode==System.Net.HttpStatusCode.Unauthorized||reply.StatusCode==System.Net.HttpStatusCode.Forbidden)
                    {error="카메라 로그인 실패 · IP Webcam 아이디·비밀번호를 확인하세요.";return;}
                    if(!reply.IsSuccessStatusCode){error="영상 응답 오류 (HTTP "+(int)reply.StatusCode+") · 영상 주소를 확인하세요.";return;}
                    string type=reply.Content.Headers.ContentType==null?"":reply.Content.Headers.ContentType.MediaType;
                    if(!type.Equals("multipart/x-mixed-replace",StringComparison.OrdinalIgnoreCase))throw new IOException("MJPEG 영상 주소가 필요합니다.");
                    using(var stream=await reply.Content.ReadAsStreamAsync().ConfigureAwait(false))
                    using(source.Token.Register(()=>stream.Dispose()))
                    {
                        var parser=new AoiCameraProtocol.Parser();var buffer=new byte[16384];
                        while(true)
                        {
                            source.CancelAfter(15000);
                            int n=await stream.ReadAsync(buffer,0,buffer.Length,source.Token).ConfigureAwait(false);
                            if(n==0)break;
                            parser.Push(buffer,n,bytes=>{AoiCameraProtocol.ValidateJpeg(bytes);lock(gate)if(session==generation)pending=bytes;});
                        }
                    }
                }
            }
        }
        catch(OperationCanceledException){error="영상 수신 시간 초과 · 주소와 휴대폰 앱을 확인하세요.";}
        catch(Exception){error="영상 연결 실패 · 주소·네트워크·MJPEG 설정을 확인하세요.";}
        finally{lock(gate)if(session==generation){running=false;pending=null;state=error;}source.Dispose();}
    }
    void Update()
    {
        byte[] bytes;AoiPreviewProtocol.Frame metadata;lock(gate){bytes=pending;metadata=pendingMetadata;pending=null;pendingMetadata=null;}
        if(bytes==null)return;
        if(!image)image=new Texture2D(2,2,TextureFormat.RGB24,false);
        if(!image.LoadImage(bytes)){Disconnect();lock(gate)state="영상 JPEG를 표시할 수 없습니다.";return;}
        receivedAt=Time.realtimeSinceStartup;lock(gate)state="실시간 영상 수신 중 · AI 판정은 별도";
        latestJpeg=bytes;displayedMetadata=metadata;sampledAt=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        if(metadata!=null){lock(gate)state="Jetson 실시간 영상 · frame "+metadata.frame_id;if(!previewTextureLogged){Debug.Log("[AOI Preview] Texture updated: frame_id="+metadata.frame_id+" size="+image.width+"x"+image.height);previewTextureLogged=true;}}
    }
    public bool TryReferencedFrame(out byte[] bytes,out string cameraId,out long frameId)
    {
        bytes=null;cameraId=null;frameId=-1;if(!CanInspectFrame||latestJpeg==null)return false;
        bytes=(byte[])latestJpeg.Clone();cameraId=displayedMetadata.camera_id;frameId=displayedMetadata.frame_id;return true;
    }
    public bool TrySnapshot(out byte[] bytes,out AoiDirectProtocol.InputImage metadata)
    {
        bytes=null;metadata=null;
        if(!Frame||latestJpeg==null||Time.realtimeSinceStartup-receivedAt>1.5f)return false;
        bytes=(byte[])latestJpeg.Clone();
        using(var sha=SHA256.Create())metadata=new AoiDirectProtocol.InputImage{mime_type="image/jpeg",byte_length=bytes.Length,width=image.width,height=image.height,sha256=BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant(),sampled_at_ms=sampledAt};
        return true;
    }
    public void Disconnect()
    {
        lock(gate){generation++;running=false;pending=null;pendingMetadata=null;previewSocket?.Abort();previewSocket=null;state="카메라 연결 해제";}
        var source=cancellation;cancellation=null;
        if(source!=null)try{source.Cancel();}catch(ObjectDisposedException){}
        receivedAt=-100;
        latestJpeg=null;displayedMetadata=null;IsJetsonPreview=false;
    }
    void OnDisable(){Disconnect();if(image){Destroy(image);image=null;}}
}
