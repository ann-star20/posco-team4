using System;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

// Desktop Unity client. Credentials stay outside Assets; Unity APIs run only in Update.
public class AoiWebSocketClient : MonoBehaviour
{
    [Serializable] class Keys { public string unity; }
    [Serializable] class LocalConfig { public Keys tokens; }
    [Serializable] class Hello { public string type="hello",role="unity",token; }
    [Serializable] public class Envelope
    {
        public int version;
        public string type,role,source,target,message_id,code;
        public AoiJetsonFeed.Packet payload;
    }
    class Event { public string json,state,reason;public bool ready; }
    public AoiJetsonFeed feed;
    public string serverUrl="ws://127.0.0.1:8765/fab";
    public string credentialFile="Tools/FabSocket/server.local.json";
    public bool Connected{get;private set;}
    public int ReceivedResults{get;private set;}
    readonly Queue<Event> incoming=new Queue<Event>();
    readonly object gate=new object();
    CancellationTokenSource lifetime;
    ClientWebSocket socket;
    readonly SemaphoreSlim sendGate=new SemaphoreSlim(1,1);
    int generation;
    bool restoreBackground;
    const int MaxBytes=4000000;
    void OnEnable()
    {
        if(!Application.isPlaying)return;
        if(!feed)feed=GetComponent<AoiJetsonFeed>();
        if(!feed)return;
        feed.useWebSocket=true;
        try
        {
            var uri=new Uri(serverUrl);
            if(uri.AbsolutePath!="/fab"||uri.Scheme!="wss"&&(uri.Scheme!="ws"||!uri.IsLoopback))throw new ArgumentException();
            string path=Path.IsPathRooted(credentialFile)?credentialFile:Path.GetFullPath(Path.Combine(Application.dataPath,"..",credentialFile));
            var config=JsonUtility.FromJson<LocalConfig>(File.ReadAllText(path));
            if(config?.tokens?.unity==null||config.tokens.unity.Length<32)throw new ArgumentException();
            restoreBackground=!Application.runInBackground;Application.runInBackground=true;
            string hello=JsonUtility.ToJson(new Hello{token=config.tokens.unity});
            lifetime=new CancellationTokenSource();int current=++generation;var cancel=lifetime.Token;
            _=Task.Run(()=>Run(uri,hello,current,cancel));
        }
        catch(Exception)
        {FeedState(false,"접속 설정 확인 필요","서버 주소·로컬 접속 키 파일을 확인해 주세요");}
    }
    void PostState(int current,bool ready,string state,string reason)
    {
        lock(gate)
        {if(current!=generation)return;if(!ready)incoming.Clear();incoming.Enqueue(new Event{ready=ready,state=state,reason=reason});}
    }
    async Task Run(Uri uri,string hello,int current,CancellationToken cancel)
    {
        while(!cancel.IsCancellationRequested)
        {
            PostState(current,false,"서버 연결 중","인증·접속 대기 · 분류 정지");
            try
            {
                using(var client=new ClientWebSocket())
                {
                    lock(gate){if(current!=generation)return;socket=client;}
                    client.Options.Proxy=null;client.Options.KeepAliveInterval=TimeSpan.FromSeconds(15);
                    using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel))
                    {
                        timeout.CancelAfter(TimeSpan.FromSeconds(6));
                        await client.ConnectAsync(uri,timeout.Token).ConfigureAwait(false);
                        byte[] auth=Encoding.UTF8.GetBytes(hello);
                        await client.SendAsync(new ArraySegment<byte>(auth),WebSocketMessageType.Text,true,timeout.Token).ConfigureAwait(false);
                        string welcome=await Receive(client,timeout.Token).ConfigureAwait(false);
                        Enqueue(current,welcome);
                    }
                    while(client.State==WebSocketState.Open&&!cancel.IsCancellationRequested)
                        Enqueue(current,await Receive(client,cancel).ConfigureAwait(false));
                }
            }
            catch(Exception)
            {
                if(cancel.IsCancellationRequested)break;
                PostState(current,false,"서버 연결 끊김","재접속 대기 · 기존 판정 해제 · 분류 정지");
            }
            finally {lock(gate){if(current==generation)socket=null;}}
            try{await Task.Delay(2000,cancel).ConfigureAwait(false);}catch(OperationCanceledException){break;}
        }
    }
    void Enqueue(int current,string json)
    {
        lock(gate)
        {
            if(current!=generation)return;
            if(incoming.Count>=16)throw new IOException("Receive queue full");
            incoming.Enqueue(new Event{json=json});
        }
    }
    static async Task<string> Receive(ClientWebSocket client,CancellationToken cancel)
    {
        var buffer=new byte[16384];
        using(var data=new MemoryStream())
        {
            WebSocketReceiveResult part;
            do
            {
                part=await client.ReceiveAsync(new ArraySegment<byte>(buffer),cancel).ConfigureAwait(false);
                if(part.MessageType!=WebSocketMessageType.Text)throw new IOException("Text message required");
                if(data.Length+part.Count>MaxBytes)throw new IOException("Message too large");
                data.Write(buffer,0,part.Count);
            }while(!part.EndOfMessage);
            return new UTF8Encoding(false,true).GetString(data.ToArray());
        }
    }
    void Update()
    {
        for(int i=0;i<4;i++)
        {
            Event next;lock(gate){if(incoming.Count==0)break;next=incoming.Dequeue();}
            if(next.json==null)
            {Connected=next.ready;FeedState(next.ready,next.state,next.reason);continue;}
            try{Handle(next.json);}
            catch(Exception)
            {Connected=false;FeedState(false,"수신 오류","잘못된 메시지 수신 · 분류 정지");AbortSocket();}
        }
    }
    void Handle(string json)
    {
        var message=JsonUtility.FromJson<Envelope>(json);
        if(message==null)throw new ArgumentException();
        if(message.type=="welcome")
        {
            if(message.role!="unity"||message.version!=1)throw new ArgumentException();
            Connected=true;FeedState(true,"서버 연결됨","WebSocket 인증 완료 · 검사 결과 대기");return;
        }
        if(message.type=="error"||message.type=="ack"||message.type=="process_status")
        {
            if(ProcessAnalysisView.Instance&&ProcessAnalysisView.Instance.HandleTransport(json))return;
            if(message.type=="error")throw new ArgumentException();
            return;
        }
        if(message.type=="process_analysis")
        {
            if(Connected&&ProcessAnalysisView.Instance)ProcessAnalysisView.Instance.Accept(json);
            return;
        }
        if(message.type!="inspection_result")return;
        if(!Connected||message.version!=1||message.source!="jetson"||message.target!="unity"||string.IsNullOrWhiteSpace(message.message_id)||message.payload==null||string.IsNullOrWhiteSpace(message.payload.frame_id))throw new ArgumentException();
        if(feed.demoMode||feed.directMode)return;
        if(feed.AcceptPacket(message.payload,false))ReceivedResults++;
    }
    public async Task<bool> SendProcessRequest(string json)
    {
        ClientWebSocket target;CancellationToken token;
        lock(gate){if(!Connected||socket==null||lifetime==null)return false;target=socket;token=lifetime.Token;}
        bool entered=false;
        try
        {
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(token))
            {
                timeout.CancelAfter(TimeSpan.FromSeconds(6));
                await sendGate.WaitAsync(timeout.Token);entered=true;
                if(target.State!=WebSocketState.Open)return false;
                byte[] bytes=Encoding.UTF8.GetBytes(json);
                if(bytes.Length>8192)return false;
                await target.SendAsync(new ArraySegment<byte>(bytes),WebSocketMessageType.Text,true,timeout.Token);
                return true;
            }
        }
        catch(Exception){return false;}
        finally{if(entered)sendGate.Release();}
    }
    void FeedState(bool ready,string state,string reason)
    {if(feed&&!feed.directMode)feed.SetTransportState(ready,state,reason);}
    void AbortSocket(){lock(gate){try{socket?.Abort();}catch(ObjectDisposedException){}}}
    void OnDisable()
    {
        if(!Application.isPlaying&&lifetime==null)return;
        lock(gate){generation++;incoming.Clear();}
        lifetime?.Cancel();AbortSocket();lifetime?.Dispose();lifetime=null;Connected=false;
        if(feed)FeedState(false,"서버 연결 끊김","통신 종료 · 분류 대기");
        if(restoreBackground){Application.runInBackground=false;restoreBackground=false;}
    }
}
