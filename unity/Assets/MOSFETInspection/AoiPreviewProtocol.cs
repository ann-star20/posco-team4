using System;
using System.IO;
using System.Net.WebSockets;
using System.Threading;
using System.Threading.Tasks;

public static class AoiPreviewProtocol
{
    public const string DefaultAddress="ws://192.168.213.167:8500/camera/preview";
    public static string UpgradeSavedAddress(string value)
    {
        if(!Uri.TryCreate(value,UriKind.Absolute,out var uri)||(uri.Scheme!="ws"&&uri.Scheme!="wss"))return value;
        if(uri.Host!="192.168.10.253"&&uri.Host!="192.168.10.184"&&uri.Host!="192.168.10.224"&&uri.Host!="192.168.55.1")return value;
        return new UriBuilder(uri){Host="192.168.213.167"}.Uri.AbsoluteUri;
    }
    [Serializable] public class Subscription
    {
        public string type="camera.preview.subscribe",camera_id="aoi-camera-1",api_token;
        public int schema_version=1,preferred_width=1280,preferred_height=720,preferred_fps=5;
    }
    [Serializable] public class Frame
    {
        public string type,camera_id,captured_at,mime_type,error_code;
        public int schema_version,width,height,byte_length;
        public long frame_id;
        public bool binary_frame_follows;
    }
    [Serializable] public class FrameRequest
    {
        public string type="aoi.inspection.requested";
        public int schema_version=1,attempt;
        public string request_id,job_id,run_id,lot_id,unit_id,camera_id,api_token;
        public long frame_id;
        public FrameRequest(AoiDirectProtocol.Request q)
        {request_id=q.request_id;job_id=q.job_id;run_id=q.run_id;lot_id=q.lot_id;unit_id=q.unit_id;attempt=q.attempt;camera_id=q.camera_id;frame_id=q.frame_id;api_token=q.api_token;}
    }
    public static Uri Address(string input)
    {
        string value=(input??"").Trim();if(value.Length==0||value.Length>512)throw new ArgumentException("Jetson IP 또는 Preview 주소를 입력하세요.");
        if(!value.Contains("://"))value="ws://"+value;
        if(!Uri.TryCreate(value,UriKind.Absolute,out var uri)||(uri.Scheme!="ws"&&uri.Scheme!="wss")||uri.UserInfo!=""||uri.Query!=""||uri.Fragment!="")throw new ArgumentException("토큰을 포함하지 않은 ws/wss 영상 주소가 필요합니다.");
        var builder=new UriBuilder(uri);if(uri.IsDefaultPort)builder.Port=8500;if(uri.AbsolutePath=="/")builder.Path="/camera/preview";
        if(builder.Path!="/camera/preview")throw new ArgumentException("Preview 경로는 /camera/preview 입니다.");return builder.Uri;
    }
    public static string InspectionAddress(string preview)
    {var builder=new UriBuilder(Address(preview)){Port=8400,Path="/aoi"};return builder.Uri.AbsoluteUri;}
    public static string SubscriptionFailure(Frame reply,string cameraId)
    {
        // Only known error codes become UI text; server messages may contain credentials.
        if(reply!=null&&reply.type=="camera.preview.rejected"&&reply.error_code=="unauthorized")return "영상 인증 거부 · 현재 Jetson의 CAMERA_PREVIEW_TOKEN을 다시 입력하세요.";
        if(reply!=null&&reply.type=="camera.preview.subscribed"&&!string.IsNullOrEmpty(reply.camera_id)&&reply.camera_id!=cameraId)return "영상 카메라 ID 불일치 · 서버의 카메라 ID를 확인하세요.";
        if(reply==null||reply.type!="camera.preview.subscribed")return "영상 구독 거부 · 영상 토큰·카메라 ID를 확인하세요.";
        return null;
    }
    public static void ValidateFrame(Frame frame,string cameraId,long previousId)
    {
        if(frame==null||frame.type!="camera.preview.frame"||frame.schema_version!=1||frame.camera_id!=cameraId||frame.frame_id<0||frame.frame_id<=previousId||!DateTimeOffset.TryParse(frame.captured_at,out _))throw new IOException("Preview camera/frame metadata mismatch");
        if(frame.width<1||frame.width>4096||frame.height<1||frame.height>4096||frame.mime_type!="image/jpeg"||frame.byte_length<4||frame.byte_length>AoiCameraProtocol.MaxBytes||!frame.binary_frame_follows)throw new IOException("Preview JPEG metadata invalid");
    }
    public static void ValidatePhoto(Frame frame,byte[] jpeg)
    {if(jpeg==null||jpeg.Length!=frame.byte_length)throw new IOException("Preview JPEG length mismatch");AoiCameraProtocol.ValidateJpeg(jpeg,frame.width,frame.height);}
    public static async Task<byte[]> Receive(WebSocket socket,WebSocketMessageType expected,int limit,CancellationToken cancel,Action<string> trace=null)
    {
        var buffer=new byte[16384];using(var stream=new MemoryStream())
        {
            WebSocketReceiveResult part;
            do
            {
                part=await socket.ReceiveAsync(new ArraySegment<byte>(buffer),cancel).ConfigureAwait(false);
                trace?.Invoke(part.MessageType+" chunk received: "+part.Count+" bytes, end="+part.EndOfMessage);
                if(part.MessageType==WebSocketMessageType.Close)throw new IOException("Preview server closed the connection");
                if(part.MessageType!=expected||stream.Length+part.Count>limit)throw new IOException("Unexpected or oversized WebSocket frame");
                stream.Write(buffer,0,part.Count);
            }while(!part.EndOfMessage);
            trace?.Invoke(expected+" complete: "+stream.Length+" bytes");
            return stream.ToArray();
        }
    }
}
