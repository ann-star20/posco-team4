using System;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Unity.Plastic.Newtonsoft.Json;
using Unity.Plastic.Newtonsoft.Json.Linq;

public static class AsyncTcadSocket
{
    public static Uri Address(string origin, string path)
    {
        var uri = new Uri(origin.Trim());
        if ((uri.Scheme!="ws" && uri.Scheme!="wss") || uri.AbsolutePath!="/" || uri.Query!="" || uri.Fragment!="" || uri.UserInfo!="")
            throw new FormatException("Gateway origin only, e.g. ws://192.168.213.12:8000");
        return new Uri(uri, path);
    }
    public static async Task<JObject> Receive(ClientWebSocket socket, CancellationToken cancel)
    {
        var bytes = new byte[16384];
        using (var data = new MemoryStream())
        {
            WebSocketReceiveResult part;
            do
            {
                part = await socket.ReceiveAsync(new ArraySegment<byte>(bytes), cancel).ConfigureAwait(false);
                if (part.MessageType!=WebSocketMessageType.Text || data.Length+part.Count>4_000_000)
                    throw new FormatException("Gateway closed stream or returned invalid/oversized text");
                data.Write(bytes,0,part.Count);
            } while (!part.EndOfMessage);
            return JObject.Parse(new UTF8Encoding(false,true).GetString(data.ToArray()));
        }
    }
    public static async Task<JObject> SendOnce(string origin, string token, JObject request, CancellationToken cancel)
    {
        if (string.IsNullOrWhiteSpace(token)) throw new FormatException("Gateway request token required");
        using (var socket = new ClientWebSocket())
        using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancel))
        {
            timeout.CancelAfter(TimeSpan.FromSeconds(30));
            socket.Options.Proxy=null;
            socket.Options.SetRequestHeader("X-Unity-Token",token);
            await socket.ConnectAsync(Address(origin,"/api/v1/control"),timeout.Token).ConfigureAwait(false);
            var bytes=Encoding.UTF8.GetBytes(request.ToString(Formatting.None));
            await socket.SendAsync(new ArraySegment<byte>(bytes),WebSocketMessageType.Text,true,timeout.Token).ConfigureAwait(false);
            var ack=await Receive(socket,timeout.Token).ConfigureAwait(false);
            if ((string)ack["type"]!="request.accepted" || (string)ack["request_id"]!=(string)request["request_id"] || !Guid.TryParse((string)ack["job_id"],out _))
                throw new FormatException("Request was not accepted or IDs differ. Do not blindly resend.");
            return ack;
        }
    }
    public static async Task<ClientWebSocket> ConnectStream(string origin, string run, long cursor, CancellationToken cancel)
    {
        if (!Guid.TryParse(run,out _) || cursor<0) throw new FormatException("Invalid run/cursor");
        var socket=new ClientWebSocket(); socket.Options.Proxy=null;
        try
        {
            using (var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel))
            {
                timeout.CancelAfter(TimeSpan.FromSeconds(10));
                await socket.ConnectAsync(Address(origin,"/api/v1/stream?run_id="+run+"&after_sequence="+cursor),timeout.Token).ConfigureAwait(false);
            }
            return socket;
        }
        catch { socket.Dispose(); throw; }
    }
}
