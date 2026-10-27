using System;
using System.IO;
using System.Text;

public static class AoiCameraProtocol
{
    public const int MaxBytes=8*1024*1024;
    public static Uri Address(string input)
    {
        string value=(input??"").Trim();
        if(value.Length==0||value.Length>512)throw new ArgumentException("카메라 주소를 입력하세요.");
        if(!value.Contains("://")){if(!value.Contains(":"))value+=":8080";value="http://"+value;}
        Uri uri;
        if(!Uri.TryCreate(value,UriKind.Absolute,out uri)||(uri.Scheme!="http"&&uri.Scheme!="https")||uri.UserInfo!=""||uri.Query!=""||uri.Fragment!="")throw new ArgumentException("인증정보 없는 HTTP 영상 주소를 입력하세요.");
        var builder=new UriBuilder(uri);
        if(uri.AbsolutePath=="/")builder.Path="/video";
        return builder.Uri;
    }
    public static void ValidateJpeg(byte[] bytes,int expectedWidth=0,int expectedHeight=0)
    {
        if(bytes==null||bytes.Length<4||bytes.Length>MaxBytes||bytes[0]!=255||bytes[1]!=216||bytes[bytes.Length-2]!=255||bytes[bytes.Length-1]!=217)throw new IOException("JPEG 형식 오류");
        for(int i=2;i+3<bytes.Length;)
        {
            if(bytes[i++]!=255)break;
            while(i<bytes.Length&&bytes[i]==255)i++;
            if(i>=bytes.Length)break;
            int marker=bytes[i++];if(marker==218||marker==217)break;
            if(marker==1||marker>=208&&marker<=215)continue;
            if(i+2>bytes.Length)break;
            int length=bytes[i]*256+bytes[i+1];
            if(length<2||i+length>bytes.Length)break;
            if(marker>=192&&marker<=207&&marker!=196&&marker!=200&&marker!=204)
            {
                if(length<8)break;
                int height=bytes[i+3]*256+bytes[i+4],width=bytes[i+5]*256+bytes[i+6];
                if(width<1||height<1||width>4096||height>4096)throw new IOException("영상 해상도는 최대 4096×4096입니다.");
                if(expectedWidth>0&&(width!=expectedWidth||height!=expectedHeight))throw new IOException("영상 JPEG와 metadata 크기가 다릅니다.");
                return;
            }
            i+=length;
        }
        throw new IOException("JPEG 크기 정보 오류");
    }
    // IP Webcam multipart JPEG frames carry Content-Length; other codecs need a separate decoder.
    public sealed class Parser
    {
        readonly MemoryStream header=new MemoryStream();
        byte[] frame;
        int offset;
        public void Push(byte[] buffer,int count,Action<byte[]> receive)
        {
            for(int i=0;i<count;i++)
            {
                if(frame!=null){frame[offset++]=buffer[i];if(offset==frame.Length){var complete=frame;frame=null;offset=0;receive(complete);}continue;}
                header.WriteByte(buffer[i]);int n=(int)header.Length;
                if(n>16384)throw new IOException("영상 헤더 크기 초과");
                var data=header.GetBuffer();
                if(n<4||data[n-4]!=13||data[n-3]!=10||data[n-2]!=13||data[n-1]!=10)continue;
                int size=0;bool jpeg=false;
                foreach(string line in Encoding.ASCII.GetString(data,0,n).Split('\n'))
                {
                    int colon=line.IndexOf(':');if(colon<0)continue;
                    string key=line.Substring(0,colon).Trim(),value=line.Substring(colon+1).Trim();
                    if(key.Equals("Content-Length",StringComparison.OrdinalIgnoreCase)&&!int.TryParse(value,out size))throw new IOException("영상 길이 오류");
                    if(key.Equals("Content-Type",StringComparison.OrdinalIgnoreCase))jpeg=value.StartsWith("image/jpeg",StringComparison.OrdinalIgnoreCase);
                }
                if(!jpeg||size<4||size>MaxBytes)throw new IOException("Content-Length가 있는 MJPEG 영상이 필요합니다.");
                frame=new byte[size];header.SetLength(0);
            }
        }
    }
}
