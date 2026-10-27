#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

[InitializeOnLoad]
public static class AoiLightUpgrade
{
    [Serializable] class Saved { public string[] responses;public string image_path; }
    const string Key="AoiLightUpgrade";
    static AoiJetsonFeed feed;
    static AoiInspectionHistory store;
    static string folder;
    static double after;
    static AoiLightUpgrade(){EditorApplication.update+=Tick;}
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static void Capture(string name)
    {
        var rt=(RenderTexture)typeof(AoiDashboard).GetField("popupTexture",BindingFlags.NonPublic|BindingFlags.Instance).GetValue(feed.dashboard);Check(rt&&rt.IsCreated(),"Popup render texture absent");
        var previous=RenderTexture.active;RenderTexture.active=rt;var image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);
        try{image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();File.WriteAllBytes("Tools/JetsonAOI/"+name+".png",image.EncodeToPNG());}finally{RenderTexture.active=previous;UnityEngine.Object.Destroy(image);}
    }
    static void Press(string name)
    {
        var camera=GameObject.Find("AOI_MONITOR_WINDOW_CAMERA").GetComponent<Camera>();var button=feed.dashboard.GetComponentsInChildren<Button>(false).First(b=>b.name==name);Check(button.interactable,"Button blocked: "+name);
        var rect=(RectTransform)button.transform;var pixel=RectTransformUtility.WorldToScreenPoint(camera,rect.TransformPoint(rect.rect.center));Check(feed.dashboard.HandlePointer(pixel,camera),"Pointer relay failed: "+name);
    }
    static void AcceptSaved(int defects,int serverAgeSeconds=0)
    {
        Saved saved=null;foreach(var path in Directory.GetFiles("Tools/JetsonAOI/DirectTestResults","*.json").OrderByDescending(File.GetLastWriteTimeUtc))
        {var candidate=JsonUtility.FromJson<Saved>(File.ReadAllText(path));if(candidate!=null&&File.Exists(candidate.image_path)){saved=candidate;break;}}
        Check(saved!=null,"Saved photo not available");var reply=saved.responses.Select(JsonUtility.FromJson<AoiDirectProtocol.Reply>).First(r=>r.type=="aoi.inspection.completed");
        reply.message_id=Guid.NewGuid().ToString();reply.request_id=Guid.NewGuid().ToString();reply.result_origin="mock";reply.occurred_at=DateTimeOffset.Now.AddSeconds(-serverAgeSeconds).ToString("O");
        if(defects>1)reply.defects=new[]{reply.defects[0],new AoiDirectProtocol.Detection{class_name="scratch",confidence=.91f,bbox_xyxy=new[]{1500f,2420f,1800f,2620f}}};
        if(defects>2)reply.defects=reply.defects.Concat(new[]{new AoiDirectProtocol.Detection{class_name="band",confidence=.89f,bbox_xyxy=new[]{1250f,2550f,1380f,2800f}}}).ToArray();
        var request=new AoiDirectProtocol.Request{request_id=reply.request_id,job_id=reply.job_id,run_id=reply.run_id,lot_id=reply.lot_id,unit_id=reply.unit_id,attempt=reply.attempt};
        AoiDirectProtocol.ValidateReply(reply,request);var photo=File.ReadAllBytes(saved.image_path);AoiDirectProtocol.ValidatePhoto(reply.image,photo);feed.AcceptDirect(reply,photo);
        feed.notice="로컬 재생 시험 · 추가 불량 좌표는 UI 시험용 · Jetson 새 요청 아님";
    }
    static void CheckProductView()
    {
        var dashboard=feed.dashboard;
        Check(dashboard.PhotoView==3,"Product view is not the default result view");
        Press("PhotoFull");Press("PhotoProduct");Check(dashboard.PhotoView==3,"Product view button failed");
        var uv=dashboard.cameraImage.uvRect;Check(uv.width<1&&uv.height<1,"Product view did not enlarge the product");
        foreach(var item in feed.current.parts??new AoiDirectProtocol.Detection[0])
        {
            if(!AoiDirectProtocol.TryRegion(item,feed.frame.width,feed.frame.height,out var region))continue;
            Check(region[0]>=uv.xMin-.0001f&&region[2]<=uv.xMax+.0001f&&1-region[3]>=uv.yMin-.0001f&&1-region[1]<=uv.yMax+.0001f,"Product view clipped a detected part");
        }
        var photo=(RectTransform)dashboard.cameraImage.transform.parent;
        Check(photo.rect.width>=500&&photo.rect.height>=480,"Signal camera area regressed");
        var list=dashboard.GetComponentsInChildren<Text>().First(t=>t.name=="DefectCode");Check(list.text.Contains("crash"),"Detection list missing accepted defect");
        var overlay=(Canvas)typeof(AoiDashboard).GetField("signalOverlay",BindingFlags.NonPublic|BindingFlags.Instance).GetValue(dashboard);
        Check(overlay&&overlay.renderMode==RenderMode.ScreenSpaceOverlay,"Signal popup must bypass scene lighting and post-processing");
        var artwork=dashboard.GetComponentsInChildren<RawImage>().First(i=>i.name=="ApprovedArtwork");Check(artwork.texture&&artwork.texture.width==2048,"Approved browser artwork missing");
    }
    static void Restore()
    {
        if(!SessionState.GetBool(Key+"-restore",false))return;Time.timeScale=1;EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"-original",true);SessionState.SetBool(Key+"-restore",false);AoiInspectionHistory.UseTestStore(null);
    }
    static void CheckLiveReturn()
    {
        var dashboard=feed.dashboard;var result=feed.current;var resultPhoto=feed.frame;
        Press("PhotoLive");Check(dashboard.PhotoView==2&&!dashboard.cameraImage.enabled,"Disconnected live view reused result photo");
        var modal=typeof(AoiDashboard).GetField("cameraSettings",BindingFlags.NonPublic|BindingFlags.Instance);
        Check((bool)modal.GetValue(dashboard),"Disconnected camera settings unavailable");modal.SetValue(dashboard,false);
        var stream=dashboard.GetComponent<AoiCameraStream>();var flags=BindingFlags.NonPublic|BindingFlags.Instance;
        var image=typeof(AoiCameraStream).GetField("image",flags);var running=typeof(AoiCameraStream).GetField("running",flags);var received=typeof(AoiCameraStream).GetField("receivedAt",flags);
        var frame=new Texture2D(4,3);var originalImage=image.GetValue(stream);var originalRunning=running.GetValue(stream);var originalReceived=received.GetValue(stream);
        try
        {
            image.SetValue(stream,frame);running.SetValue(stream,true);received.SetValue(stream,Time.realtimeSinceStartup);
            Press("PhotoProduct");Press("PhotoLive");
            Check(dashboard.PhotoView==2&&dashboard.cameraImage.texture==frame&&dashboard.cameraImage.enabled,"Result-to-live button did not restore camera frame");
            Check(!(bool)modal.GetValue(dashboard),"Connected live return opened settings");
            Press("PhotoProduct");Check(dashboard.cameraImage.texture==resultPhoto,"Live return lost result photo");Press("PhotoLive");
            Check(dashboard.cameraImage.texture==frame&&feed.current==result,"Repeated live return changed inspection result");
        }
        finally{image.SetValue(stream,originalImage);running.SetValue(stream,originalRunning);received.SetValue(stream,originalReceived);UnityEngine.Object.Destroy(frame);modal.SetValue(dashboard,false);dashboard.SetPhotoView(0);}
    }
    static void CheckScanPresentation()
    {
        var dashboard=feed.dashboard;var flags=BindingFlags.NonPublic|BindingFlags.Instance;
        var root=(GameObject)typeof(AoiDashboard).GetField("scanRoot",flags).GetValue(dashboard);
        var tiles=(Image[])typeof(AoiDashboard).GetField("scanTiles",flags).GetValue(dashboard);
        var start=typeof(AoiDashboard).GetField("scanStarted",flags);
        var update=typeof(AoiDashboard).GetMethod("UpdateScanPresentation",flags);
        var result=feed.current;string label=result.label,verdict=result.direct_verdict;var defects=result.defects;
        try
        {
            foreach(bool normal in new[]{false,true})
            {
                dashboard.SetPhotoView(0);dashboard.BeginScanPresentation(feed.frame.EncodeToJPG());
                Check(root.activeSelf&&tiles.Length==16,"Scan grid missing");
                Check(dashboard.cameraImage.enabled&&dashboard.cameraImage.texture!=feed.frame,"Inspection frame not frozen independently");
                var frozen=dashboard.cameraImage.texture;dashboard.Refresh();Check(dashboard.cameraImage.texture==frozen,"Frozen frame changed");
                start.SetValue(dashboard,Time.realtimeSinceStartup-1.5f);update.Invoke(dashboard,null);
                Check(tiles.Count(t=>t.gameObject.activeSelf)>=8&&tiles.Count(t=>t.gameObject.activeSelf)<=9,"Grid progression incorrect");
                start.SetValue(dashboard,Time.realtimeSinceStartup-4f);update.Invoke(dashboard,null);
                Check(root.activeSelf&&tiles.All(t=>t.gameObject.activeSelf),"Slow response ended scan early");
                Check(!dashboard.GetComponentsInChildren<Button>(true).First(b=>b.name=="PhotoLive").interactable,"Live view allowed during scan");
                result.label=normal?"normal":label;result.direct_verdict=normal?"OK":verdict;result.defects=normal?Array.Empty<AoiDirectProtocol.Detection>():defects;
                dashboard.EndScanPresentation(true);
                Check(dashboard.PhotoView==3&&!root.activeSelf&&dashboard.cameraImage.texture==feed.frame,"OK/NG scan did not switch to product result");
                Check(dashboard.GetComponentsInChildren<Button>(true).First(b=>b.name=="PhotoLive").interactable,"Live return remained blocked after inspection");
            }
            dashboard.SetPhotoView(0);dashboard.BeginScanPresentation(feed.frame.EncodeToJPG());dashboard.EndScanPresentation(false);
            Check(dashboard.PhotoView==0&&!root.activeSelf,"Failed inspection fabricated product transition");
        }
        finally{result.label=label;result.direct_verdict=verdict;result.defects=defects;dashboard.EndScanPresentation(false);dashboard.SetPhotoView(3);}
    }
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;int phase=SessionState.GetInt(Key,0);
        // A refresh or manual Play stop can interrupt the previous check between phases.
        if(phase!=0&&!EditorApplication.isPlayingOrWillChangePlaymode&&File.Exists("AoiLightUpgrade.once")){SessionState.SetInt(Key,0);Restore();phase=0;}
        if(phase==0&&!EditorApplication.isPlayingOrWillChangePlaymode)Restore();
        try
        {
            if(phase==0)
            {
                if(!File.Exists("AoiLightUpgrade.once"))return;if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("AoiLightUpgrade.once");folder="Temp/AoiLightChecks-"+Guid.NewGuid().ToString("N");AoiHistoryChecks.Run(folder);
                var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();Check(scene.path=="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity","Open cleanroom scene");
                string backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeAoiLight_"+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".unity");Check(EditorSceneManager.SaveScene(scene,backup,true),"Scene backup failed");
                feed=UnityEngine.Object.FindAnyObjectByType<AoiJetsonFeed>();Check(feed&&feed.dashboard,"AOI monitor unavailable");feed.dashboard.Build(feed);EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Scene save failed");
                File.WriteAllText("AoiLightUpgrade.status","Scene backed up: "+backup+"\nDashboard installed. Runtime verification pending.");
                SessionState.SetString(Key+"-folder",folder);SessionState.SetBool(Key+"-original",EditorSettings.enterPlayModeOptionsEnabled);SessionState.SetBool(Key+"-restore",true);EditorSettings.enterPlayModeOptionsEnabled=false;SessionState.SetInt(Key,1);SessionState.SetFloat(Key+"-deadline",(float)EditorApplication.timeSinceStartup+210);EditorApplication.isPlaying=true;return;
            }
            if(!Application.isPlaying)return;
            if(phase==1)
            {
                feed=UnityEngine.Object.FindAnyObjectByType<AoiJetsonFeed>();if(!feed||!feed.GetComponent<AoiDirectClient>()||!feed.dashboard)return;
                folder=SessionState.GetString(Key+"-folder","");store=new AoiInspectionHistory(Path.Combine(folder,"play.json"));AoiInspectionHistory.UseTestStore(store);
                Check(feed.directMode&&feed.current==null&&!feed.CanSort,"Waiting state unsafe");AoiPreviewChecks.Run(feed.dashboard);feed.dashboard.Refresh();feed.dashboard.ToggleWindow();Time.timeScale=5;after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&EditorApplication.timeSinceStartup>after)
            {
                Capture("AOI_Light_Wait");Check(feed.dashboard.TodaySummary.Contains("0")&&!feed.dashboard.TodaySummary.Contains("%"),"Empty normal rate must be dash");feed.SetMode(true);feed.Demo("normal");Check(feed.Verdict=="OK"&&feed.CanSort&&feed.dashboard.DetailCount==0,"DEMO OK failed");after=EditorApplication.timeSinceStartup+.7;SessionState.SetInt(Key,3);
            }
            else if(phase==3&&EditorApplication.timeSinceStartup>after)
            {Capture("AOI_Light_OK");Press("SortProduct");Check(feed.Busy,"Native sort button failed");SessionState.SetInt(Key,4);}
            else if(phase==4&&!feed.Busy)
            {
                Check(feed.SortCompleted&&!feed.CanSort&&feed.sorter.okCount==1&&Vector3.Distance(feed.sorter.product.position,feed.sorter.okTray)<.001f,"OK sorting/duplicate gate broken");
                foreach(string label in new[]{"crash","band","scratch"}){feed.Demo(label);Check(feed.Verdict=="NG"&&feed.CanSort,"DEMO defect mapping failed: "+label);}
                Check(store.ForDay(DateTime.Today,"demo").total==4&&store.ForDay(DateTime.Today,"demo").normalRate==25,"DEMO daily counts wrong");Press("SortProduct");SessionState.SetInt(Key,5);
            }
            else if(phase==5&&!feed.Busy)
            {
                Check(feed.SortCompleted&&!feed.CanSort&&feed.sorter.ngCount==1&&Vector3.Distance(feed.sorter.product.position,feed.sorter.ngTray)<.001f,"NG sort failed");
                feed.SetMode(false);AcceptSaved(1);Check(feed.Verdict=="NG"&&feed.dashboard.DetailCount==1,"Single saved region missing");after=EditorApplication.timeSinceStartup+.7;SessionState.SetInt(Key,6);
            }
            else if(phase==6&&EditorApplication.timeSinceStartup>after)
            {CheckProductView();CheckScanPresentation();Capture("AOI_Light_NG");feed.dashboard.BeginScanPresentation(feed.frame.EncodeToJPG());after=EditorApplication.timeSinceStartup+1.45;SessionState.SetInt(Key,9);}
            else if(phase==9&&EditorApplication.timeSinceStartup>after)
            {Capture("AOI_Scan_Progress");after=EditorApplication.timeSinceStartup+1.8;SessionState.SetInt(Key,10);}
            else if(phase==10&&EditorApplication.timeSinceStartup>after)
            {Capture("AOI_Scan_Wait");feed.dashboard.EndScanPresentation(true);AcceptSaved(2);Check(feed.dashboard.DetailCount==2&&store.ForDay(DateTime.Today,"mock").total==2,"Two defects must count as one additional inspection");Press("SelectDefect1");Check(feed.dashboard.SelectedDefect==1&&feed.dashboard.PhotoView==1&&feed.dashboard.cameraImage.uvRect.width<1,"Second crop selection failed");after=EditorApplication.timeSinceStartup+.7;SessionState.SetInt(Key,7);}
            else if(phase==7&&EditorApplication.timeSinceStartup>after)
            {
                Capture("AOI_Light_TwoDefects");Press("PhotoFull");Check(feed.dashboard.cameraImage.uvRect.width==1,"Original view failed");CheckLiveReturn();Press("PhotoFull");
                AcceptSaved(3);Press("DefectNext");Press("SelectDefect0");Check(feed.dashboard.SelectedDefect==2,"Third defect paging failed");Press("DefectPrevious");
                for(int i=0;i<6;i++)store.Add(new AoiInspectionHistory.Entry{result_id="HISTORY-"+i,inspection_id=Guid.NewGuid().ToString(),completed_at=DateTimeOffset.Now.AddSeconds(i).ToString("O"),unit_id="MOSFET-TEST-"+i,lot_id="TEST-LOT",verdict=i%2==0?"OK":"NG",label=i%2==0?"normal":"crash",source="mock",confidence=.9f});
                store.Add(new AoiInspectionHistory.Entry{result_id="YESTERDAY",inspection_id=Guid.NewGuid().ToString(),completed_at=DateTimeOffset.Now.AddDays(-1).ToString("O"),unit_id="TEST",verdict="OK",label="normal",source="mock",confidence=.9f});
                Press("ViewHistory");Check(feed.dashboard.View==1,"History tab failed");Press("HistoryRow0");Press("HistoryNextPage");Press("HistoryPreviousPage");Press("HistoryFilter");Press("HistoryFilter");Press("HistoryFilter");Press("HistoryFilter");Press("HistoryPreviousDay");Press("HistoryNextDay");
                Check(new AoiInspectionHistory(store.FilePath).ForDay(DateTime.Today,"mock").total==9,"Runtime history not durable");after=EditorApplication.timeSinceStartup+.7;SessionState.SetInt(Key,8);
            }
            else if(phase==8&&EditorApplication.timeSinceStartup>after)
            {
                Capture("AOI_Light_History");Press("ViewInspection");Check(feed.GetComponent<AoiWebSocketClient>()&&feed.GetComponent<AoiDirectClient>()&&!feed.GetComponent<AoiDirectClient>().HasToken,"Transport or token lifetime changed");
                AcceptSaved(1,40);Check(feed.current.captured_at_ms<AoiJetsonFeed.Now-30000&&feed.Fresh&&feed.CanSort,"Jetson clock skew blocked a newly correlated reply or overwrote its original timestamp");
                var receipt=typeof(AoiJetsonFeed).GetField("directReceivedAt",BindingFlags.NonPublic|BindingFlags.Instance);var received=receipt.GetValue(feed);receipt.SetValue(feed,Time.realtimeSinceStartupAsDouble-feed.maxAgeSeconds-1);
                Check(!feed.Fresh&&!feed.CanSort&&feed.SortBlockReason.Contains("유효시간"),"Direct reply expiry was bypassed");receipt.SetValue(feed,received);
                feed.current.label="normal";feed.current.direct_verdict="OK";feed.current.defects=Array.Empty<AoiDirectProtocol.Detection>();
                SessionState.SetInt(Key+"-auto-ok",feed.sorter.okCount+1);SessionState.SetInt(Key+"-auto-ng",feed.sorter.ngCount+1);
                Check(feed.BeginInspectionCycle(),"Automatic inspection did not start");Check(!feed.BeginInspectionCycle()&&!feed.CanSort,"Duplicate inspection or premature manual sort allowed");feed.ResolveInspectionCycle(true);SessionState.SetInt(Key,11);
            }
            else if(phase==11&&!feed.InspectionCycleRunning&&!feed.Busy)
            {
                Check(feed.SortCompleted&&feed.sorter.okCount==SessionState.GetInt(Key+"-auto-ok",-1)&&Vector3.Distance(feed.sorter.product.position,feed.sorter.okTray)<.001f&&!feed.CanSort,"Automatic OK route or duplicate gate failed");
                AcceptSaved(1,40);feed.current.label="bend";Check(feed.BeginInspectionCycle(),"Automatic NG start failed");feed.ResolveInspectionCycle(true);SessionState.SetInt(Key,12);
            }
            else if(phase==12&&!feed.InspectionCycleRunning&&!feed.Busy)
            {
                Check(feed.SortCompleted&&feed.sorter.ngCount==SessionState.GetInt(Key+"-auto-ng",-1)&&Vector3.Distance(feed.sorter.product.position,feed.sorter.ngTray)<.001f&&!feed.CanSort,"Automatic NG route or bend mapping failed");
                AcceptSaved(1);Check(feed.BeginInspectionCycle(),"Slow inspection start failed");after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,13);
            }
            else if(phase==13&&EditorApplication.timeSinceStartup>after)
            {
                Check(feed.InspectionCycleRunning&&feed.sorter.InspectionReady&&!feed.Busy&&!feed.CanSort&&Vector3.Distance(feed.sorter.product.position,feed.sorter.inspection)<.001f,"Equipment did not hold at inspection while waiting for Jetson");
                feed.ResolveInspectionCycle(false);Check(!feed.InspectionCycleRunning&&!feed.sorter.Running&&!feed.sorter.product.gameObject.activeSelf,"Failed inspection did not stop equipment");
                AcceptSaved(1);feed.current.confidence=.1f;Check(feed.BeginInspectionCycle(),"Low-confidence cycle start failed");feed.ResolveInspectionCycle(true);SessionState.SetInt(Key,14);
            }
            else if(phase==14&&!feed.InspectionCycleRunning&&!feed.Busy)
            {
                Check(!feed.SortCompleted&&feed.sorter.Status.StartsWith("HOLD")&&feed.sorter.okCount==SessionState.GetInt(Key+"-auto-ok",-1)&&feed.sorter.ngCount==SessionState.GetInt(Key+"-auto-ng",-1),"Failed or low-confidence inspection was delivered");
                File.WriteAllText("AoiLightUpgrade.result","AOI_LIGHT_RUNTIME_OK\nBackup and scene saved. WAIT/OK/NG, normal/crash/band/scratch DEMO, actual OK/NG tray animation, duplicate block, saved JPEG replay, one/two/three defect crop + paging + pointer relay, original/zoom/live-wait distinction, result-to-live return without settings and preserved result, frozen scan frame with 16-cell progression and slow-response wait, OK/NG product auto-view and failure recovery, automatic equipment feed-inspect-OK/NG route with wait/failure/low-confidence/duplicate gates, 40-second Jetson clock skew with preserved server timestamp and enforced local receipt expiry, Jetson preview displayed-frame binding and frame-only requests, local durable history, daily normal rate, source/day isolation and corrupt/unwritable handling passed.\nTests used a separate Temp archive; production statistics were not seeded. No authenticated new Jetson request or real-time camera test.\n");File.AppendAllText("AoiLightUpgrade.status","\nRuntime verification passed; isolated test archive only.");SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
            }
            if(phase>0&&EditorApplication.timeSinceStartup>SessionState.GetFloat(Key+"-deadline",float.MaxValue))throw new Exception("AOI light runtime check timed out");
        }
        catch(Exception e){File.WriteAllText("AoiLightUpgrade.result","FAILED: "+e);SessionState.SetInt(Key,0);Time.timeScale=1;EditorApplication.isPlaying=false;Debug.LogException(e);}
    }
}
#endif
