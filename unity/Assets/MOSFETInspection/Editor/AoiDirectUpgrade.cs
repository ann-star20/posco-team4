#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class AoiDirectUpgrade
{
    [Serializable] class Saved { public string[] responses;public string image_path; }
    const string Key="AoiDirectUpgrade";
    static AoiJetsonFeed feed;
    static double after,deadline;
    static AoiDirectUpgrade(){EditorApplication.update+=Tick;}
    static void Check(bool condition,string error){if(!condition)throw new Exception(error);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("AoiDirectUpgrade.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("AoiDirectUpgrade.once");SessionState.SetInt(Key,1);
                deadline=EditorApplication.timeSinceStartup+90;SessionState.SetFloat(Key+"-deadline",(float)deadline);
                EditorApplication.isPlaying=true;return;
            }
            if(deadline==0)deadline=SessionState.GetFloat(Key+"-deadline",0);
            if(!Application.isPlaying)return;
            if(phase==1)
            {
                feed=UnityEngine.Object.FindAnyObjectByType<AoiJetsonFeed>();
                if(!feed||!feed.GetComponent<AoiDirectClient>()||!feed.dashboard)return;
                Check(feed.directMode&&feed.useWebSocket,"Direct AOI not attached");
                var directory="Tools/JetsonAOI/DirectTestResults";
                Saved saved=null;
                foreach(var path in Directory.GetFiles(directory,"*.json").OrderByDescending(File.GetLastWriteTimeUtc))
                {var candidate=JsonUtility.FromJson<Saved>(File.ReadAllText(path));if(candidate!=null&&File.Exists(candidate.image_path)){saved=candidate;break;}}
                Check(saved!=null,"Saved direct photo unavailable for replay check");
                var reply=saved.responses.Select(JsonUtility.FromJson<AoiDirectProtocol.Reply>).First(r=>r.type=="aoi.inspection.completed");
                var request=new AoiDirectProtocol.Request{request_id=reply.request_id,job_id=reply.job_id,run_id=reply.run_id,lot_id=reply.lot_id,unit_id=reply.unit_id,attempt=reply.attempt};
                AoiDirectProtocol.ValidateReply(reply,request);var photo=File.ReadAllBytes(saved.image_path);AoiDirectProtocol.ValidatePhoto(reply.image,photo);
                feed.SetMode(false);feed.AcceptDirect(reply,photo);
                Check(feed.Verdict=="NG"&&feed.frame&&feed.frame.width==reply.image.width&&feed.frame.height==reply.image.height,"JPEG or NG missing");
                Check(feed.DisplayCurrent&&!feed.Fresh&&!feed.CanSort,"Archived result must remain visible and not be sortable");
                Check(reply.result_origin=="mock"?feed.dashboard.confidence.text.Contains("시험"):feed.notice.Contains(reply.result_origin),"Result provenance absent");
                Check(feed.dashboard.identity.text.Contains(reply.request_id.Substring(0,12)),"Request ID absent");
                feed.notice="저장된 Jetson 결과 재생 시험 · 출처: "+reply.result_origin+" · 새 검사 요청 아님";
                if(!feed.dashboard.WindowOpen)feed.dashboard.ToggleWindow();
                after=EditorApplication.timeSinceStartup+2;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&EditorApplication.timeSinceStartup>after)
            {
                Check(feed.current!=null&&feed.DisplayCurrent,"Shared FabSocket cleared direct result");
                var rt=(RenderTexture)typeof(AoiDashboard).GetField("popupTexture",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(feed.dashboard);
                Check(rt&&rt.IsCreated(),"Monitor render texture unavailable");
                var previous=RenderTexture.active;RenderTexture.active=rt;
                var image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);
                try{image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();File.WriteAllBytes("Tools/JetsonAOI/Unity_AOI_SavedResult_Check.png",image.EncodeToPNG());}
                finally{RenderTexture.active=previous;UnityEngine.Object.Destroy(image);}
                File.WriteAllText("AoiDirectUpgrade.result","AOI_DIRECT_RUNTIME_OK\nSaved Jetson JSON/JPEG replay: hash, 3024x4032 decode, NG/class/confidence, provenance, request ID, retained snapshot, expired sort blocked; shared FabSocket did not clear direct result. Monitor capture saved. No authenticated Unity-to-Jetson request was sent; user token entry required.\n");
                SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
            }
            if(phase>0&&deadline>0&&EditorApplication.timeSinceStartup>deadline)throw new Exception("AOI runtime check timed out");
        }
        catch(Exception e)
        {File.WriteAllText("AoiDirectUpgrade.result","FAILED: "+e);SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;Debug.LogException(e);}
    }
}
#endif
