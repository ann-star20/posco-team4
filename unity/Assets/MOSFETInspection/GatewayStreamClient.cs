using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Net.WebSockets;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

// Read-only DB event subscription. This client has no control/approval/apply sender.
public class GatewayStreamClient : MonoBehaviour
{
    [Serializable] public class Result {public double vth,gm,id_on,id,bv;public bool vth_present,gm_present,bv_present;}
    [Serializable] public class Ratios {public double dose,epi,tox;}
    [Serializable] public class OutputUnits {public string vth,gm,id_on,bv;}
    [Serializable] public class Metadata {public string note,representation;public Ratios input_ratios;public OutputUnits units;}
    [Serializable] public class ServerError {public string code,message;}
    [Serializable] public class Response {public string status,result_origin,model_version,request_id,job_id,error_code,error_message;public ServerError error;public Result result_payload;public Metadata metadata;}
    [Serializable] public class Payload {public string job_id,request_id,lot_id,unit_id,verdict;public Response response;}
    [Serializable] public class DbEvent {public long sequence;public string event_id,run_id,event_type,source,occurred_at;public Payload payload;[NonSerialized] public bool hasId,hasIdOn;[NonSerialized] public string rawJson;}
    public string endpoint="ws://192.168.212.10:8000/api/v1/stream";
    public string runId="0ec2d043-e626-4bdf-a2b7-3bed42d4941a";
    public readonly List<DbEvent> Events=new List<DbEvent>();
    public event Action<DbEvent> EventReceived;
    public DbEvent LatestElectrical {get;private set;}
    public long LastSequence {get;private set;}
    public string Status {get;private set;}="Gateway 연결 전";
    public string Error {get;private set;}
    public bool Connected {get;private set;}
    public bool Reconnecting=>lifetime!=null;
    public string ActiveRun {get;private set;}
    string activeEndpoint;
    CancellationTokenSource lifetime;
    readonly object gate=new object();
    readonly Queue<string> received=new Queue<string>();
    string nextStatus;
    bool nextConnected;
    int generation;
    bool overflow;
    const int MaxMessage=4_000_000;
    public static Uri StreamUri(string address,string run,long sequence)
    {
        if(!Guid.TryParse(run,out var id)||sequence<0)throw new ArgumentException("RUN ID는 UUID여야 합니다.");
        var b=new UriBuilder(address.Trim());
        if((b.Scheme!="ws"&&b.Scheme!="wss")||!string.IsNullOrEmpty(b.UserName)||!string.IsNullOrEmpty(b.Password)||b.Path!="/api/v1/stream"||!string.IsNullOrEmpty(b.Query)||!string.IsNullOrEmpty(b.Fragment))throw new ArgumentException("Gateway /api/v1/stream 주소를 입력하세요.");
        b.Query="run_id="+id.ToString()+"&after_sequence="+sequence;return b.Uri;
    }
    public static DbEvent Parse(string json,string run)
    {
        var e=JsonUtility.FromJson<DbEvent>(json);
        if(e==null||e.sequence<=0||!Guid.TryParse(e.event_id,out _)||!Guid.TryParse(e.run_id,out var eventRun)||!Guid.TryParse(run,out var expected)||eventRun!=expected||string.IsNullOrWhiteSpace(e.event_type))throw new FormatException("Gateway 이벤트의 RUN ID·sequence·event_id를 확인하세요.");
        e.rawJson=json;
        var result=Regex.Match(json,"\"result_payload\"\\s*:\\s*\\{([^{}]*)\\}");
        var response=e.payload?.response;
        if(response!=null)
        {
            // JsonUtility can construct a zero-filled class for JSON null. Read presence from the wire.
            response.result_payload=null;
            if(response.status=="succeeded"&&result.Success)
            {
                string body=result.Groups[1].Value;
                var r=new Result();
                r.vth_present=ReadNumber(body,"vth",out r.vth);r.gm_present=ReadNumber(body,"gm",out r.gm);r.bv_present=ReadNumber(body,"bv",out r.bv);
                e.hasId=ReadNumber(body,"id",out r.id);e.hasIdOn=ReadNumber(body,"id_on",out r.id_on);
                if(r.vth_present||r.gm_present||r.bv_present||e.hasId||e.hasIdOn)response.result_payload=r;
            }
        }
        return e;
    }
    static bool ReadNumber(string body,string key,out double number)
    {
        number=0;
        var match=Regex.Match(body,"(?:^|,)\\s*\""+key+"\"\\s*:\\s*(-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\\s*(?=,|$)");
        return match.Success&&double.TryParse(match.Groups[1].Value,NumberStyles.Float,CultureInfo.InvariantCulture,out number)&&!double.IsNaN(number)&&!double.IsInfinity(number);
    }
    public bool ConnectStream()
    {
        try
        {
            StreamUri(endpoint,runId,0);DisconnectStream();
            string canonical=Guid.Parse(runId).ToString();
            if(ActiveRun!=canonical||activeEndpoint!=endpoint){Events.Clear();LastSequence=0;LatestElectrical=null;}
            ActiveRun=canonical;activeEndpoint=endpoint;Error=null;Status="Gateway 연결 중";
            lifetime=new CancellationTokenSource();int version=++generation;var cancel=lifetime.Token;
            _=Task.Run(()=>ReceiveLoop(version,cancel));return true;
        }
        catch(Exception e){Error=e.Message;Status="연결 설정 확인 필요";return false;}
    }
    void Post(int version,string status,bool connected)
    {lock(gate){if(version!=generation)return;nextStatus=status;nextConnected=connected;}}
    async Task ReceiveLoop(int version,CancellationToken cancel)
    {
        while(!cancel.IsCancellationRequested)
        {
            try
            {
                long cursor;lock(gate)cursor=LastSequence;
                using(var socket=new ClientWebSocket())
                {
                    socket.Options.Proxy=null;socket.Options.KeepAliveInterval=TimeSpan.FromSeconds(15);
                    using(var connect=CancellationTokenSource.CreateLinkedTokenSource(cancel))
                    {connect.CancelAfter(TimeSpan.FromSeconds(8));await socket.ConnectAsync(StreamUri(activeEndpoint,ActiveRun,cursor),connect.Token).ConfigureAwait(false);}
                    Post(version,"Gateway 연결됨 · DB 이벤트 수신 대기",true);
                    var buffer=new byte[65536];
                    while(socket.State==WebSocketState.Open&&!cancel.IsCancellationRequested)
                    {
                        using(var message=new MemoryStream())
                        {
                            WebSocketReceiveResult part;
                            do
                            {
                                part=await socket.ReceiveAsync(new ArraySegment<byte>(buffer),cancel).ConfigureAwait(false);
                                if(part.MessageType==WebSocketMessageType.Close)throw new IOException("Gateway 연결 종료");
                                if(part.MessageType!=WebSocketMessageType.Text)throw new FormatException("JSON text 이벤트가 필요합니다.");
                                if(message.Length+part.Count>MaxMessage)throw new FormatException("이벤트 크기 제한 초과");
                                message.Write(buffer,0,part.Count);
                            }while(!part.EndOfMessage);
                            string raw=Encoding.UTF8.GetString(message.ToArray());
                            lock(gate)
                            {
                                if(version!=generation)return;
                                if(received.Count>=128){overflow=true;throw new IOException("이벤트 처리 지연");}
                                received.Enqueue(raw);
                            }
                        }
                    }
                }
            }
            catch(Exception e)
            {
                if(cancel.IsCancellationRequested)return;
                Post(version,"Gateway 재접속 대기 · "+e.GetType().Name,false);
            }
            try{await Task.Delay(2000,cancel).ConfigureAwait(false);}catch(OperationCanceledException){return;}
        }
    }
    public bool ApplyEvent(string json)
    {
        try
        {
            var e=Parse(json,ActiveRun??runId);
            lock(gate)
            {
                if(e.sequence<=LastSequence)return false;
                if(Events.Exists(x=>x.event_id==e.event_id))throw new FormatException("같은 이벤트 ID에 다른 sequence가 수신되었습니다.");
                Events.Add(e);if(Events.Count>32)Events.RemoveAt(0);
                if(e.event_type=="surrogate.completed"&&e.payload?.response?.status=="succeeded"&&e.payload.response.result_payload!=null)LatestElectrical=e;
                LastSequence=e.sequence;
            }
            Error=null;EventReceived?.Invoke(e);return true;
        }
        catch(Exception e){Error=e.Message;return false;}
    }
    void Update(){Pump();}
    public void Pump()
    {
        lock(gate){if(nextStatus!=null){Status=nextStatus;Connected=nextConnected;nextStatus=null;}}
        for(int i=0;i<32;i++)
        {
            string json;lock(gate){if(received.Count==0)break;json=received.Dequeue();}
            if(!ApplyEvent(json)&&Error!=null){DisconnectStream();Status="이벤트 확인 필요 · "+Error;break;}
        }
        lock(gate){if(overflow){Error="수신 대기열 초과 · 마지막 sequence부터 다시 연결하세요.";overflow=false;}}
    }
    public void DisconnectStream()
    {
        lock(gate){generation++;received.Clear();nextStatus=null;}
        lifetime?.Cancel();lifetime?.Dispose();lifetime=null;Connected=false;Status="Gateway 연결 해제";
    }
    void OnDisable(){DisconnectStream();}
}
