using System;
using System.Net;
using System.Net.Http;

public static class AoiCameraAuth
{
    public static HttpClientHandler Create(Uri uri,string user,string password)
    {
        if(uri==null||(uri.Scheme!="http"&&uri.Scheme!="https")||uri.UserInfo.Length!=0)throw new ArgumentException("카메라 주소 오류");
        user=user??"";password=password??"";
        if(user.Length>256||password.Length>512||user.IndexOfAny(new[]{'\r','\n','\0'})>=0)throw new ArgumentException("카메라 로그인 입력 오류");
        if(user.Length==0&&password.Length!=0)throw new ArgumentException("카메라 아이디를 입력하세요.");
        var handler=new HttpClientHandler{AllowAutoRedirect=false,UseProxy=false,UseDefaultCredentials=false,PreAuthenticate=false};
        if(user.Length!=0)
        {
            // Respond only to this camera's Digest challenge; never fall back to Basic over HTTP.
            var credentials=new CredentialCache();credentials.Add(uri,"Digest",new NetworkCredential(user,password));handler.Credentials=credentials;
        }
        return handler;
    }
}
