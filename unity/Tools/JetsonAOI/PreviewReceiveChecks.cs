using System;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

public static class PreviewReceiveChecks
{
    sealed class Socket : WebSocket
    {
        readonly Queue<Tuple<WebSocketMessageType,byte[]>> messages=new Queue<Tuple<WebSocketMessageType,byte[]>>();
        int offset;
        bool receiving;
        public void Add(WebSocketMessageType type,byte[] bytes){messages.Enqueue(Tuple.Create(type,bytes));}
        public override WebSocketCloseStatus? CloseStatus=>null;
        public override string CloseStatusDescription=>null;
        public override WebSocketState State=>WebSocketState.Open;
        public override string SubProtocol=>null;
        public override void Abort(){}
        public override void Dispose(){}
        public override Task CloseAsync(WebSocketCloseStatus status,string description,CancellationToken token)=>Task.CompletedTask;
        public override Task CloseOutputAsync(WebSocketCloseStatus status,string description,CancellationToken token)=>Task.CompletedTask;
        public override Task SendAsync(ArraySegment<byte> buffer,WebSocketMessageType type,bool end,CancellationToken token)=>Task.CompletedTask;
        public override async Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer,CancellationToken token)
        {
            if(receiving)throw new Exception("Concurrent receives");
            receiving=true;
            try
            {
                await Task.Yield();token.ThrowIfCancellationRequested();
                var message=messages.Peek();int count=Math.Min(Math.Min(buffer.Count,7000),message.Item2.Length-offset);
                Array.Copy(message.Item2,offset,buffer.Array,buffer.Offset,count);offset+=count;
                bool end=offset==message.Item2.Length;if(end){messages.Dequeue();offset=0;}
                return new WebSocketReceiveResult(count,message.Item1,end);
            }
            finally{receiving=false;}
        }
    }
    public static async Task Run()
    {
        var socket=new Socket();var photo=new byte[70001];for(int i=0;i<photo.Length;i++)photo[i]=(byte)(i%251);
        var ack=Encoding.UTF8.GetBytes("{\"type\":\"camera.preview.subscribed\"}");
        var metadata=Encoding.UTF8.GetBytes("{\"type\":\"camera.preview.frame\",\"frame_id\":7713}");
        socket.Add(WebSocketMessageType.Text,ack);socket.Add(WebSocketMessageType.Text,metadata);socket.Add(WebSocketMessageType.Binary,photo);
        socket.Add(WebSocketMessageType.Text,metadata);socket.Add(WebSocketMessageType.Binary,photo);
        var received=await AoiPreviewProtocol.Receive(socket,WebSocketMessageType.Text,65536,CancellationToken.None);
        if(Encoding.UTF8.GetString(received)!=Encoding.UTF8.GetString(ack))throw new Exception("Approval mismatch");
        int fragments=0;
        for(int frame=0;frame<2;frame++)
        {
            received=await AoiPreviewProtocol.Receive(socket,WebSocketMessageType.Text,65536,CancellationToken.None);
            if(Encoding.UTF8.GetString(received)!=Encoding.UTF8.GetString(metadata))throw new Exception("Metadata mismatch");
            received=await AoiPreviewProtocol.Receive(socket,WebSocketMessageType.Binary,100000,CancellationToken.None,s=>{if(s.Contains("chunk received"))fragments++;});
            if(received.Length!=photo.Length)throw new Exception("Truncated JPEG");
            for(int i=0;i<photo.Length;i++)if(received[i]!=photo[i])throw new Exception("Corrupt JPEG");
        }
        if(fragments<4)throw new Exception("Fragment path not exercised");
        socket.Add(WebSocketMessageType.Close,new byte[0]);
        try{await AoiPreviewProtocol.Receive(socket,WebSocketMessageType.Text,65536,CancellationToken.None);throw new Exception("Close accepted");}catch(IOException){}
    }
}
