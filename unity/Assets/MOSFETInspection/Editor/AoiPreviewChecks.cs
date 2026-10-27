#if UNITY_EDITOR
using System;
using System.Linq;
using System.Reflection;
using UnityEngine;

public static class AoiPreviewChecks
{
    static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
    public static void Run(AoiDashboard dashboard)
    {
        var stream=dashboard.GetComponent<AoiCameraStream>();if(!stream)stream=dashboard.gameObject.AddComponent<AoiCameraStream>();
        Check(!stream.Running,"Preview check requires an isolated disconnected stream");
        string[] names={"image","running","receivedAt","latestJpeg","displayedMetadata","pending","pendingMetadata","state","<IsJetsonPreview>k__BackingField"};
        var fields=names.Select(n=>typeof(AoiCameraStream).GetField(n,BindingFlags.NonPublic|BindingFlags.Instance)).ToArray();var originals=fields.Select(f=>f.GetValue(stream)).ToArray();
        void Set(string name,object value){fields[Array.IndexOf(names,name)].SetValue(stream,value);}
        var image=new Texture2D(8,6,TextureFormat.RGB24,false);image.Apply();var jpeg=image.EncodeToJPG();
        try
        {
            Set("image",image);Set("running",true);Set("receivedAt",Time.realtimeSinceStartup);Set("latestJpeg",jpeg);Set("<IsJetsonPreview>k__BackingField",true);
            var shown=new AoiPreviewProtocol.Frame{type="camera.preview.frame",schema_version=1,camera_id="aoi-camera-1",frame_id=645,width=8,height=6,mime_type="image/jpeg",byte_length=jpeg.Length,binary_frame_follows=true,captured_at=DateTimeOffset.UtcNow.ToString("O")};
            Set("displayedMetadata",shown);Set("pending",jpeg);Set("pendingMetadata",new AoiPreviewProtocol.Frame{camera_id="aoi-camera-1",frame_id=646});
            Check(stream.TryReferencedFrame(out var snapshot,out var cameraId,out var frameId)&&frameId==645&&cameraId==shown.camera_id,"Inspection selected pending frame instead of displayed frame");
            Check(!ReferenceEquals(snapshot,jpeg)&&snapshot.SequenceEqual(jpeg),"Inspection snapshot did not retain the displayed JPEG");
            var request=new AoiDirectProtocol.Request{camera_id=cameraId,frame_id=frameId,api_token="test-only"};
            var json=JsonUtility.ToJson(new AoiPreviewProtocol.FrameRequest(request));
            Check(json.Contains("\"frame_id\":645")&&!json.Contains("input_image")&&!json.Contains("fixture_name"),"Frame request regressed to image upload/fixture mode");
            shown.frame_id=647;Check(frameId==645,"In-flight inspection frame changed with preview");
            Set("receivedAt",Time.realtimeSinceStartup-2);Check(!stream.CanInspectFrame&&!stream.TryReferencedFrame(out _,out _,out _),"Stale preview still inspectable");
            Set("running",false);Check(stream.FrameId==-1&&!stream.CanInspectFrame,"Disconnected preview retained inspectable ID");
            Array.Clear(snapshot,0,snapshot.Length);
        }
        finally{for(int i=0;i<fields.Length;i++)fields[i].SetValue(stream,originals[i]);UnityEngine.Object.Destroy(image);Array.Clear(jpeg,0,jpeg.Length);}
    }
}
#endif
