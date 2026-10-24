$ErrorActionPreference='Stop'
Add-Type -Path "$PSScriptRoot/../../Assets/MOSFETInspection/AoiCameraProtocol.cs"
function Check($ok,$name){if(-not $ok){throw $name}; "PASS: $name"}
Check ([AoiCameraProtocol]::Address('192.168.1.2').AbsoluteUri -eq 'http://192.168.1.2:8080/video') 'IP-only default'
Check ([AoiCameraProtocol]::Address('http://192.168.1.2:9000').AbsoluteUri -eq 'http://192.168.1.2:9000/video') 'Explicit port'
Check ([AoiCameraProtocol]::Address('https://camera.local/live').AbsolutePath -eq '/live') 'Explicit stream path'
foreach($bad in @('','file:///test','http://name:secret@camera/video','http://camera/video?token=secret')){
 $blocked=$false; try{[AoiCameraProtocol]::Address($bad)|Out-Null}catch{$blocked=$true}; Check $blocked 'Invalid or credential address blocked'
}
$jpg=[byte[]](255,216,255,192,0,17,8,0,16,0,32,3,1,17,0,2,17,0,3,17,0,255,217)
[AoiCameraProtocol]::ValidateJpeg($jpg)
$header=[Text.Encoding]::ASCII.GetBytes("--frame`r`nContent-Type: image/jpeg`r`nContent-Length: $($jpg.Length)`r`n`r`n")
$parser=New-Object AoiCameraProtocol+Parser
$pack=[byte[]]($header+$jpg+$header+$jpg)
$script:seen=0
$receive=[Action[byte[]]]{param($frame) [AoiCameraProtocol]::ValidateJpeg($frame); $script:seen++}
foreach($b in $pack){$parser.Push([byte[]]@($b),1,$receive)}
Check ($script:seen -eq 2) 'Fragmented multipart frames and consecutive frames'
$parser=New-Object AoiCameraProtocol+Parser
$bad=[Text.Encoding]::ASCII.GetBytes("--frame`r`nContent-Length: 999999999`r`n`r`n")
$blocked=$false;try{$parser.Push($bad,$bad.Length,$receive)}catch{$blocked=$true};Check $blocked 'Oversize frame blocked'
$jpg[9]=255; $blocked=$false;try{[AoiCameraProtocol]::ValidateJpeg($jpg)}catch{$blocked=$true};Check $blocked 'Oversize decoded image blocked'
