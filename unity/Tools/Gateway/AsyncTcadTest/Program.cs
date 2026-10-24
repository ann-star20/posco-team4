using System;
using System.Threading;
using System.Threading.Tasks;
using Unity.Plastic.Newtonsoft.Json.Linq;

class Program
{
    static async Task Main(string[] args)
    {
        if (args.Length>0 && args[0]=="--live") { await LiveGateway.Run(); return; }
        Console.WriteLine(AsyncTcadChecks.Run());
        if (args.Length==0) return;
        if (args[0]!="--socket") throw new Exception("Only --socket local fixture supported");
        using var mock=new MockGateway();
        const string origin="ws://127.0.0.1:18765";
        string run=Guid.NewGuid().ToString(), request=Guid.NewGuid().ToString();
        using (var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(15)))
        {
            var body=AsyncTcadContract.Build(System.IO.File.ReadAllText(System.IO.Path.Combine(AppContext.BaseDirectory,"diagnosis-input.example.json")),run,request,"LOT-TEST","UNIT-TEST");
            var ack=await AsyncTcadSocket.SendOnce(origin,"local-test-token",body,timeout.Token);
            var state=new AsyncTcadContract.State(run,request,(string)ack["job_id"]);
            using (var first=await AsyncTcadSocket.ConnectStream(origin,run,0,timeout.Token))
                state.Accept(await AsyncTcadSocket.Receive(first,timeout.Token));
            if (state.Sequence!=1 || state.Candidates.Count!=1) throw new Exception("Initial queued event missing");
            using (var replay=await AsyncTcadSocket.ConnectStream(origin,run,state.Sequence,timeout.Token))
            {
                state.Accept(await AsyncTcadSocket.Receive(replay,timeout.Token));
                state.Accept(await AsyncTcadSocket.Receive(replay,timeout.Token));
            }
            if (state.Sequence!=3 || state.Candidates.Count!=1 || state.Batch==null) throw new Exception("Resume lost candidate/batch");
            await mock.Work;
            Console.WriteLine("ASYNC_TCAD_SOCKET_OK: authenticated diagnosis request / fragmented UTF-8 messages / resume after sequence / no resubmit. Local mock Gateway; no DB or TCAD execution.");
        }
    }
}
