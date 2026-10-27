$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot '../../Assets/MOSFETInspection/AoiDirectProtocol.cs')
function Check($condition, $name) { if (-not $condition) { throw $name }; Write-Output ('PASS: ' + $name) }
Check ([AoiDirectProtocol]::FailureReason('authentication_failed') -ne [AoiDirectProtocol]::FailureReason('frame_time_invalid')) 'Authentication and clock failures distinguished'
Check (-not [AoiDirectProtocol]::FailureReason('untrusted-secret-text').Contains('untrusted-secret-text')) 'Unknown server error text not exposed'
$request = New-Object AoiDirectProtocol+Request
$request.request_id='request'; $request.job_id='job'; $request.run_id='run'
$reply = New-Object AoiDirectProtocol+Reply
$reply.type='aoi.inspection.completed'; $reply.schema_version=1
$reply.request_id='request'; $reply.job_id='job'; $reply.run_id='run'
$reply.lot_id=$request.lot_id; $reply.unit_id=$request.unit_id; $reply.attempt=1
$reply.message_id='message'; $reply.verdict='fail'; $reply.result_origin='mock'
$reply.occurred_at='2026-10-19T06:00:00+00:00'
$reply.defects=@((New-Object AoiDirectProtocol+Detection))
$reply.defects[0].class_name='crash'; $reply.defects[0].confidence=0.87
$reply.image=New-Object AoiDirectProtocol+ImageInfo
$reply.image.mime_type='image/jpeg'; $reply.image.width=3024; $reply.image.height=4032
$reply.image.binary_frame_follows=$true
$photo=[byte[]](255,216,255,192,0,17,8,15,192,11,208,3,1,17,0,2,17,0,3,17,0,255,217)
$reply.image.byte_length=$photo.Length
$sha=[Security.Cryptography.SHA256]::Create()
try { $reply.image.sha256=[BitConverter]::ToString($sha.ComputeHash($photo)).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
[AoiDirectProtocol]::ValidateReply($reply,$request)
[AoiDirectProtocol]::ValidatePhoto($reply.image,$photo)
Check ([AoiDirectProtocol]::NeedsPhoto($reply)) 'Nested image flag; full resolution photo metadata accepted'
Check ([AoiDirectProtocol]::Label($reply) -eq 'crash') 'Crash mapping'
Check ([Math]::Abs([AoiDirectProtocol]::Confidence($reply)-0.87) -lt 0.001) 'Detection confidence'
$reply.request_id='other'; $blocked=$false
try { [AoiDirectProtocol]::ValidateReply($reply,$request) } catch { $blocked=$true }
Check $blocked 'Wrong request blocked'; $reply.request_id='request'
$photo[4]=9; $blocked=$false
try { [AoiDirectProtocol]::ValidatePhoto($reply.image,$photo) } catch { $blocked=$true }
Check $blocked 'Corrupt photo blocked'
$reply.verdict='pass'; $blocked=$false
try { [AoiDirectProtocol]::ValidateReply($reply,$request) } catch { $blocked=$true }
Check $blocked 'Contradictory pass with defects blocked'
$reply.verdict='fail'; $reply.defects[0].class_name='unknown'
Check ([AoiDirectProtocol]::Label($reply) -eq 'unknown') 'Unknown defect preserved for review'
$reply.result_origin=$null; $blocked=$false
try { [AoiDirectProtocol]::ValidateReply($reply,$request) } catch { $blocked=$true }
Check $blocked 'Missing source rejected'
$reply.result_origin='prod'; $reply.verdict='pass'; $reply.defects=$null
$reply.parts=@((New-Object AoiDirectProtocol+Detection))
$reply.parts[0].class_name='body'; $reply.parts[0].confidence=0.98
[AoiDirectProtocol]::ValidateReply($reply,$request)
Check ([AoiDirectProtocol]::Label($reply) -eq 'normal') 'Pass maps to normal'
Check ([Math]::Abs([AoiDirectProtocol]::Confidence($reply)-0.98) -lt 0.001) 'Pass uses part detection confidence'
$d=New-Object AoiDirectProtocol+Detection
$d.bbox_xyxy=[float[]](1229,1932,1867,2273); $region=$null
Check ([AoiDirectProtocol]::TryRegion($d,3024,4032,[ref]$region)) 'Defect coordinates available'
Check ([Math]::Abs($region[1]-1932.0/4032) -lt 0.0001) 'Top-origin coordinates normalized'
$d.bbox_xyxy=[float[]](-1,0,20,20)
Check (-not [AoiDirectProtocol]::TryRegion($d,3024,4032,[ref]$region)) 'Outside-image coordinates rejected'
$d.bbox_xyxy=[float[]](10,10,5,20)
Check (-not [AoiDirectProtocol]::TryRegion($d,3024,4032,[ref]$region)) 'Reversed coordinates rejected'
$d.bbox_xyxy=$null
Check (-not [AoiDirectProtocol]::TryRegion($d,3024,4032,[ref]$region)) 'Missing coordinates do not invent locations'
$reply.verdict='review'; $reply.parts=$null
[AoiDirectProtocol]::ValidateReply($reply,$request)
Check ([AoiDirectProtocol]::Label($reply) -eq 'unknown') 'No product stays review, never normal'
$request.input_source='unity_camera'; $request.input_image=New-Object AoiDirectProtocol+InputImage
$request.input_image.sha256=('a'*64)
$reply.input_source='unity_camera'; $reply.input_image_sha256=('b'*64)
$blocked=$false;try{[AoiDirectProtocol]::ValidateReply($reply,$request)}catch{$blocked=$true}
Check $blocked 'Another camera frame cannot satisfy current inspection'
$reply.input_image_sha256=$request.input_image.sha256
[AoiDirectProtocol]::ValidateReply($reply,$request)
Check $true 'Matching camera frame accepted'
