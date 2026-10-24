#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.Networking;
using Unity.Plastic.Newtonsoft.Json.Linq;

[InitializeOnLoad] public static class GatewayApprovalWindowCheck
{
    const string Key="GatewayApprovalWindowCheckPhase";
    [Serializable] class Bootstrap {public string token,endpoint,request_json;public string[] events;}
    static UnityWebRequest bootstrap;
    static GatewayTcadApprovalView view;
    static GatewayInspectionBridge bridge;
    static GatewayInspectionBridge.Job job;
    static int jobCount;
    static double deadline,after;
    const BindingFlags Fields=BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public;
    static GatewayApprovalWindowCheck(){EditorApplication.update+=Tick;}
    static object Get(object owner,string field)=>owner.GetType().GetField(field,Fields).GetValue(owner);
    static void Require(bool ok,string why){if(!ok)throw new InvalidOperationException(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        if(phase!=0&&!EditorApplication.isPlayingOrWillChangePlaymode&&File.Exists("GatewayApprovalWindowCheck.once")){SessionState.SetInt(Key,0);phase=0;deadline=0;}
        try
        {
            if(phase==0)
            {
                if(!File.Exists("GatewayApprovalWindowCheck.once")||EditorApplication.isPlayingOrWillChangePlaymode)return;
                SessionState.SetString(Key+"Bootstrap",File.ReadAllText("GatewayApprovalWindowCheck.once").Trim());File.Delete("GatewayApprovalWindowCheck.once");
                PlayerSettings.insecureHttpOption=InsecureHttpOption.DevelopmentOnly;AssetDatabase.SaveAssets();
                Require(PlayerSettings.insecureHttpOption==InsecureHttpOption.DevelopmentOnly,"HTTP must be DevelopmentOnly");
                SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(!Application.isPlaying)return;
            if(deadline==0)deadline=EditorApplication.timeSinceStartup+90;
            Require(EditorApplication.timeSinceStartup<deadline,"Approval window display check timed out");
            if(phase==1)
            {
                bridge=GatewayInspectionBridge.Instance;if(!bridge)return;
                var gameType=typeof(Editor).Assembly.GetType("UnityEditor.GameView");
                if(gameType!=null){var game=EditorWindow.GetWindow(gameType);game.Show();game.Focus();}
                jobCount=bridge.Jobs.Count;bootstrap=UnityWebRequest.Get(SessionState.GetString(Key+"Bootstrap",""));bootstrap.timeout=15;bootstrap.SendWebRequest();SessionState.SetInt(Key,2);return;
            }
            if(phase==2)
            {
                if(!bootstrap.isDone)return;
                Require(bootstrap.result==UnityWebRequest.Result.Success,"Temporary test context unavailable");
                var data=JsonUtility.FromJson<Bootstrap>(bootstrap.downloadHandler.text);bootstrap.Dispose();bootstrap=null;
                bridge.Token=data.token;bridge.StreamAddress=data.endpoint;data.token=null;
                var request=JsonUtility.FromJson<GatewayInspectionProtocol.Request>(data.request_json);var original=JObject.Parse(data.request_json);
                var provenance=original["input_payload"]?["provenance"];var inspection=provenance?["inspection_result"];
                string physical=(string)(inspection?["thickness_verdict"]??inspection?["dose_verdict"]),electrical=(string)inspection?["electrical_verdict"];
                job=new GatewayInspectionBridge.Job{request=request,streamAddress=data.endpoint,inspectionId=(string)provenance?["inspection_id"],kind="gateway_full_cycle"};
                job.cycle=new GatewayFullCycleProtocol.State(request.run_id,request.request_id,request.lot_id,request.unit_id,physical=="OK",electrical=="OK",electrical=="OK"||electrical=="NG");
                view=GatewayTcadApprovalView.For(bridge);
                foreach(string raw in data.events)
                {
                    var e=JObject.Parse(raw);string type=(string)e["event_type"];
                    if(type=="diagnosis.completed")
                    {
                        Require(job.cycle.PendingDiagnosis,"Recorded inspection is not eligible for diagnosis");job.cycle.DiagnosisJson();
                        typeof(GatewayFullCycleProtocol.State).GetProperty("DiagnosisId").SetValue(job.cycle,(string)e["payload"]["request_id"]);
                    }
                    if(type=="tcad.verification.review_required"){view.Observe(job,raw);job.cycle.ObserveReviewEvent(raw);}
                    else job.cycle.Accept(raw);
                    job.rawEvent=raw;
                }
                Require(job.cycle.ReviewRequired,"No actual review_required event in received history");
                // The replay job is deliberately not registered with Bridge.Jobs: no control submissions.
                SessionState.SetInt(Key,3);return;
            }
            if(phase==3)
            {
                if((bool)Get(view,"busy")||Get(view,"active")==null||view.LastWindowPaintFrame<0)return;
                Require((bool)Get(view,"open"),"Candidate review window closed");
                var group=(GatewayTcadApprovalProtocol.Proposal)Get(Get(view,"active"),"proposal");
                Require(group.proposal_id==job.cycle.ProposalId&&group.run_id==job.cycle.Run&&group.job_id==job.cycle.DiagnosisJob,"Wrong proposal displayed");
                Require(group.candidates.Length>0,"Candidate list empty");
                Directory.CreateDirectory("Tools/Previews");ScreenCapture.CaptureScreenshot("Tools/Previews/Gateway-Candidate-Window.png");
                after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,4);return;
            }
            if(phase==4&&EditorApplication.timeSinceStartup>after)
            {
                var review=Get(view,"active");var group=(GatewayTcadApprovalProtocol.Proposal)Get(review,"proposal");
                int selected=Array.FindIndex(group.candidates,GatewayTcadApprovalProtocol.Eligible);
                Require(selected>=0,"No normal candidate available for administrator dialog display check");
                review.GetType().GetField("selected",Fields).SetValue(review,selected);
                view.GetType().GetField("actor",Fields).SetValue(view,"화면 표시 점검");
                view.GetType().GetMethod("BeginAdmin",Fields).Invoke(view,new object[]{review,true});
                after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,5);return;
            }
            if(phase==5&&EditorApplication.timeSinceStartup>after)
            {
                Require(view.LastAdminPaintFrame>=0&&Get(view,"adminReview")!=null,"Administrator modal did not render");
                Require((string)Get(view,"password")=="","Display check entered a password");Require(!job.cycle.DecisionReceived,"Display check sent a decision");
                Require(bridge.Jobs.Count==jobCount,"Display check registered a new inspection");
                ScreenCapture.CaptureScreenshot("Tools/Previews/Gateway-Admin-Password-Window.png");
                after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,6);return;
            }
            if(phase==6&&EditorApplication.timeSinceStartup>after)
            {
                Require(File.Exists("Tools/Previews/Gateway-Candidate-Window.png")&&File.Exists("Tools/Previews/Gateway-Admin-Password-Window.png"),"Game screenshots missing");
                File.WriteAllText("GatewayApprovalWindowCheck.result","GATEWAY_APPROVAL_WINDOW_VISIBLE_OK\n"+DateTime.UtcNow.ToString("O")+"\nRUN: "+job.cycle.Run+"\nProposal: "+job.cycle.ProposalId+"\nActual received history replay + Unity GET of Gateway review list + real OnGUI candidate/admin modal repaint + Game screenshots.\nNo new inspection, password confirmation, approval or rejection submission.\nPlay remains on with administrator dialog open.");
                SessionState.SetInt(Key,0);deadline=0;
            }
        }
        catch(Exception e)
        {
            bootstrap?.Dispose();bootstrap=null;SessionState.SetInt(Key,0);deadline=0;
            File.WriteAllText("GatewayApprovalWindowCheck.result","FAILED\n"+e);Debug.LogException(e);
        }
    }
}
#endif
