using System;
using System.Security.Cryptography;

// Wire contract observed from the AOI /aoi endpoint; independent of Unity rendering.
public static class AoiDirectProtocol
{
    public const int MaxImageBytes=16*1024*1024;
    [Serializable] public class Request
    {
        public string type="aoi.inspection.requested";
        public int schema_version=1;
        public string request_id=Guid.NewGuid().ToString(),job_id=Guid.NewGuid().ToString(),run_id=Guid.NewGuid().ToString();
        public string lot_id="LOT-UNITY-TEST-001",unit_id="MOSFET-TEST-001";
        public int attempt=1;
        public string fixture_name="test_aoi_mosfet1.jpg",api_token;
        public string input_source;
        public InputImage input_image;
        public string camera_id;
        public long frame_id;
    }
    [Serializable] public class InputImage : ImageInfo { public long sampled_at_ms; }
    [Serializable] public class Detection { public string class_name;public float confidence;public float[] bbox_xyxy; }
    [Serializable] public class ImageInfo
    {
        public string image_id,mime_type,sha256;
        public int byte_length,width,height;
        public bool binary_frame_follows;
    }
    [Serializable] public class Reply
    {
        public string type,message_id,request_id,job_id,run_id,lot_id,unit_id,result_origin,verdict,occurred_at,error_code;
        public int schema_version,attempt;
        public bool binary_frame_follows,defect_detected;
        public float processing_ms;
        public Detection[] parts,defects;
        public ImageInfo image;
        public string input_source,input_image_sha256;
        public string camera_id,persistence_status;
        public long frame_id;
    }
    public static bool NeedsPhoto(Reply r) { return r.binary_frame_follows || r.image!=null&&r.image.binary_frame_follows; }
    public static string FailureReason(string code)
    {
        switch(code)
        {
            case "authentication_failed":return "검사 토큰 불일치 · 현재 서버의 토큰을 다시 입력하세요";
            case "frame_time_invalid":return "PC·Jetson 시각 차이 또는 오래된 사진 · 두 장치 시각 확인 필요";
            case "frame_not_found":case "frame_expired":return "Jetson에 해당 프레임이 없음 · 최신 영상으로 다시 검사하세요";
            case "camera_not_found":case "camera_unavailable":return "Jetson 카메라 ID·영상 서버 상태를 확인하세요";
            case "image_integrity_failed":return "전송 사진 손상 · 새 화면으로 다시 검사하세요";
            case "image_decode_failed":return "Jetson에서 사진을 읽지 못함";
            case "job_image_conflict":return "검사 ID 중복 · 새 검사 요청 필요";
            default:return "Jetson 내부 검사 실패 · 모델 추론·사진 처리 확인 필요";
        }
    }
    public static void ValidateReply(Reply r,Request q)
    {
        if(r==null||r.type!="aoi.inspection.completed"||r.schema_version!=1||r.request_id!=q.request_id||r.job_id!=q.job_id||r.run_id!=q.run_id||r.lot_id!=q.lot_id||r.unit_id!=q.unit_id||r.attempt!=q.attempt)throw new ArgumentException("검사 요청과 결과 ID 불일치");
        DateTimeOffset timestamp;
        if(string.IsNullOrWhiteSpace(r.message_id)||r.message_id.Length>100||string.IsNullOrWhiteSpace(r.result_origin)||!DateTimeOffset.TryParse(r.occurred_at,out timestamp))throw new ArgumentException("결과 ID·출처·검사 시각 누락");
        if(r.verdict!="pass"&&r.verdict!="fail"&&r.verdict!="review")throw new ArgumentException("알 수 없는 검사 판정");
        if(q.input_source=="unity_camera"&&(q.input_image==null||r.input_source!="unity_camera"||!string.Equals(r.input_image_sha256,q.input_image.sha256,StringComparison.OrdinalIgnoreCase)))throw new ArgumentException("현재 화면 검사 결과 불일치");
        if(!string.IsNullOrEmpty(q.camera_id)&&(r.result_origin!="prod"||!string.IsNullOrEmpty(r.camera_id)&&(r.camera_id!=q.camera_id||r.frame_id!=q.frame_id)))throw new ArgumentException("실제 모델 출처 또는 요청 프레임 불일치");
        if(r.verdict=="pass"&&(r.defect_detected||r.defects!=null&&r.defects.Length>0))throw new ArgumentException("정상 판정과 불량 목록 모순");
        foreach(var group in new[]{r.parts,r.defects})if(group!=null)foreach(var d in group)
            if(d==null||string.IsNullOrWhiteSpace(d.class_name)||float.IsNaN(d.confidence)||float.IsInfinity(d.confidence)||d.confidence<0||d.confidence>1)throw new ArgumentException("검출 데이터 오류");
        if(!NeedsPhoto(r)||r.image==null||r.image.mime_type!="image/jpeg"||r.image.byte_length<=0||r.image.byte_length>MaxImageBytes||r.image.width<=0||r.image.width>4096||r.image.height<=0||r.image.height>4096||r.image.sha256==null||r.image.sha256.Length!=64)throw new ArgumentException("검사 JPEG 메타데이터 누락·크기 초과");
    }
    public static void ValidatePhoto(ImageInfo info,byte[] photo)
    {
        if(info==null||photo==null||photo.Length!=info.byte_length||photo.Length>MaxImageBytes||photo.Length<4||photo[0]!=255||photo[1]!=216||photo[2]!=255||photo[photo.Length-2]!=255||photo[photo.Length-1]!=217)throw new ArgumentException("JPEG 길이·형식 불일치");
        using(var sha=SHA256.Create())
            if(!string.Equals(BitConverter.ToString(sha.ComputeHash(photo)).Replace("-",""),info.sha256,StringComparison.OrdinalIgnoreCase))throw new ArgumentException("JPEG 해시 불일치");
        // Check the encoded dimensions before Unity allocates a decoded texture.
        for(int offset=2;offset+3<photo.Length;)
        {
            if(photo[offset++]!=255)throw new ArgumentException("JPEG 마커 오류");
            while(offset<photo.Length&&photo[offset]==255)offset++;
            if(offset>=photo.Length)break;
            int marker=photo[offset++];
            if(marker==217||marker==218)break;
            if(marker==1||marker>=208&&marker<=215)continue;
            if(offset+2>photo.Length)break;
            int length=photo[offset]*256+photo[offset+1];
            if(length<2||offset+length>photo.Length)break;
            if(marker>=192&&marker<=207&&marker!=196&&marker!=200&&marker!=204)
            {
                if(length<8||photo[offset+3]*256+photo[offset+4]!=info.height||photo[offset+5]*256+photo[offset+6]!=info.width)throw new ArgumentException("JPEG 인코딩 크기 불일치");
                return;
            }
            offset+=length;
        }
        throw new ArgumentException("JPEG 크기 정보를 찾을 수 없음");
    }
    public static string Label(Reply r)
    {
        if(r.verdict=="pass")return "normal";
        Detection top=null;
        if(r.defects!=null)foreach(var d in r.defects)if(top==null||d.confidence>top.confidence)top=d;
        return top==null?"unknown":top.class_name;
    }
    public static float Confidence(Reply r)
    {
        float value=0;var detections=r.verdict=="pass"?r.parts:r.defects;
        if(detections!=null)foreach(var d in detections)value=Math.Max(value,d.confidence);
        return value;
    }
    public static bool TryRegion(Detection d,int width,int height,out float[] region)
    {
        region=null;var b=d==null?null:d.bbox_xyxy;
        if(width<=0||height<=0||b==null||b.Length!=4)return false;
        foreach(float v in b)if(float.IsNaN(v)||float.IsInfinity(v))return false;
        if(b[0]<0||b[1]<0||b[2]>width||b[3]>height||b[0]>=b[2]||b[1]>=b[3])return false;
        region=new[]{b[0]/width,b[1]/height,b[2]/width,b[3]/height};return true;
    }
}
