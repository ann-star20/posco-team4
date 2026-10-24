param([int]$Port)
$ErrorActionPreference='Stop'
Add-Type -Path "$PSScriptRoot/../../Assets/MOSFETInspection/AoiCameraAuth.cs" -ReferencedAssemblies System.Net.Http
function Check($ok,$name){if(-not $ok){throw $name}; "PASS: $name"}
function Fetch($path,$password){
 $uri=[Uri]"http://127.0.0.1:$Port/$path"
 $handler=[AoiCameraAuth]::Create($uri,'test-camera-user',$password)
 $client=New-Object Net.Http.HttpClient($handler)
 $client.Timeout=[TimeSpan]::FromSeconds(6)
 try{ $result=$client.GetAsync($uri).GetAwaiter().GetResult(); return [int]$result.StatusCode }finally{$client.Dispose()}
}
Check ((Fetch 'video' 'test-camera-password') -eq 200) 'Digest login challenge succeeds'
Check ((Fetch 'video' 'wrong-test-password') -eq 401) 'Wrong password stays unauthorized'
Check ((Fetch 'basic' 'test-camera-password') -eq 401) 'No Basic credential fallback'
Check ((Fetch 'redirect' 'test-camera-password') -eq 302) 'Redirect not followed'
$uri=[Uri]"http://127.0.0.1:$Port/video"
$handler=[AoiCameraAuth]::Create($uri,'test-camera-user','test-camera-password')
Check ($null -eq $handler.Credentials.GetCredential([Uri]'http://other.invalid/video','Digest')) 'Credentials scoped to requested camera'
Check ($null -eq $handler.Credentials.GetCredential($uri,'Basic')) 'Digest credentials only'
$handler.Dispose()
