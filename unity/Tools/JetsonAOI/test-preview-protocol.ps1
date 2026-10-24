$ErrorActionPreference='Stop'
$root=Join-Path $PSScriptRoot '../../Assets/MOSFETInspection'
Add-Type -Path @((Join-Path $root 'AoiDirectProtocol.cs'),(Join-Path $root 'AoiCameraProtocol.cs'),(Join-Path $root 'AoiPreviewProtocol.cs'))
function Check($value,$label){if(-not $value){throw $label};Write-Output "PASS: $label"}
function Reject($action,$label){$blocked=$false;try{& $action}catch{$blocked=$true};Check $blocked $label}
Check ([AoiPreviewProtocol]::DefaultAddress -eq 'ws://192.168.213.167:8500/camera/preview') 'Current Jetson default address'
$ack=[AoiPreviewProtocol+Frame]::new();$ack.type='camera.preview.rejected';$ack.error_code='unauthorized'
Check ([AoiPreviewProtocol]::SubscriptionFailure($ack,'aoi-camera-1').Contains('영상 인증 거부')) 'Unauthorized is identified as preview token rejection'
$ack.type='camera.preview.subscribed';$ack.camera_id='another-camera';$ack.error_code=$null
Check ([AoiPreviewProtocol]::SubscriptionFailure($ack,'aoi-camera-1').Contains('카메라 ID 불일치')) 'Camera mismatch is distinct from token rejection'
$ack.camera_id='aoi-camera-1'
Check ($null -eq [AoiPreviewProtocol]::SubscriptionFailure($ack,'aoi-camera-1')) 'Valid subscription accepted'
Check ([AoiPreviewProtocol]::Address('192.168.213.167').AbsoluteUri -eq 'ws://192.168.213.167:8500/camera/preview') 'Jetson IP selects 8500 preview'
Check ([AoiPreviewProtocol]::InspectionAddress('ws://192.168.213.167:8500/camera/preview') -eq 'ws://192.168.213.167:8400/aoi') 'Preview and inspection use the same Jetson'
Reject {[AoiPreviewProtocol]::Address('http://192.168.10.111:8080/video')} 'Phone MJPEG is not silently used as Jetson preview'
Reject {[AoiPreviewProtocol]::Address('ws://user:password@localhost:8500/camera/preview')} 'Credentials in URL rejected'
Reject {[AoiPreviewProtocol]::Address('ws://localhost:8500/camera/preview?token=test')} 'Token in URL rejected'
$photo=[IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'DirectTestResults/aoi-e44da33f-9d35-4bb0-ab49-646ba79267b3.jpg'))
$frame=[AoiPreviewProtocol+Frame]::new();$frame.type='camera.preview.frame';$frame.schema_version=1;$frame.camera_id='aoi-camera-1';$frame.frame_id=645;$frame.captured_at=[DateTimeOffset]::UtcNow.ToString('O');$frame.width=3024;$frame.height=4032;$frame.mime_type='image/jpeg';$frame.byte_length=$photo.Length;$frame.binary_frame_follows=$true
[AoiPreviewProtocol]::ValidateFrame($frame,'aoi-camera-1',644);[AoiPreviewProtocol]::ValidatePhoto($frame,$photo)
Check $true 'Preview metadata and JPEG pair accepted'
Reject {[AoiPreviewProtocol]::ValidateFrame($frame,'another-camera',644)} 'Wrong camera rejected'
Reject {[AoiPreviewProtocol]::ValidateFrame($frame,'aoi-camera-1',645)} 'Repeated or reordered frame rejected'
$frame.byte_length--;Reject {[AoiPreviewProtocol]::ValidatePhoto($frame,$photo)} 'Wrong binary length rejected';$frame.byte_length++
$frame.width=1280;Reject {[AoiPreviewProtocol]::ValidatePhoto($frame,$photo)} 'JPEG dimensions must match frame metadata';$frame.width=3024
$q=[AoiDirectProtocol+Request]::new();$q.camera_id='aoi-camera-1';$q.frame_id=645;$q.api_token='test-only';$wire=[AoiPreviewProtocol+FrameRequest]::new($q)
Check ($wire.frame_id -eq 645 -and $wire.camera_id -eq 'aoi-camera-1') 'Inspection selects displayed camera and frame'
Check ($null -eq $wire.PSObject.Properties['input_image'] -and $null -eq $wire.PSObject.Properties['fixture_name']) 'Frame request contains no upload or fixture fields'
$next=[AoiDirectProtocol+Request]::new();Check ($next.request_id -ne $q.request_id -and $next.job_id -ne $q.job_id -and $next.run_id -ne $q.run_id) 'All request UUIDs regenerated'
$r=[AoiDirectProtocol+Reply]::new();$r.type='aoi.inspection.completed';$r.schema_version=1;$r.request_id=$q.request_id;$r.job_id=$q.job_id;$r.run_id=$q.run_id;$r.lot_id=$q.lot_id;$r.unit_id=$q.unit_id;$r.attempt=1;$r.message_id='test-result';$r.occurred_at=[DateTimeOffset]::UtcNow.ToString('O');$r.result_origin='prod';$r.verdict='review';$r.image=[AoiDirectProtocol+ImageInfo]::new();$r.image.mime_type='image/jpeg';$r.image.byte_length=$photo.Length;$r.image.width=3024;$r.image.height=4032;$r.image.sha256='a'*64;$r.image.binary_frame_follows=$true
[AoiDirectProtocol]::ValidateReply($r,$q);Check $true 'Correlated production reply accepted without undocumented frame echo requirement'
$r.result_origin='mock';Reject {[AoiDirectProtocol]::ValidateReply($r,$q)} 'Mock result cannot satisfy production frame inspection';$r.result_origin='prod'
$r.camera_id='aoi-camera-1';$r.frame_id=644;Reject {[AoiDirectProtocol]::ValidateReply($r,$q)} 'Mismatched frame echo rejected';$r.frame_id=645
[AoiDirectProtocol]::ValidateReply($r,$q);Check $true 'Matching frame echo accepted'
$r.request_id='another-request';Reject {[AoiDirectProtocol]::ValidateReply($r,$q)} 'Wrong request rejected'
Write-Output 'PREVIEW_PROTOCOL_OK'

Check ([AoiPreviewProtocol]::UpgradeSavedAddress('ws://192.168.213.167:8500/camera/preview') -eq [AoiPreviewProtocol]::DefaultAddress) 'Old saved Jetson host migrated'
Check ([AoiPreviewProtocol]::UpgradeSavedAddress('wss://192.168.10.224:8500/camera/preview') -eq 'wss://192.168.213.167:8500/camera/preview') 'Migration preserves scheme and port'
Check ([AoiPreviewProtocol]::UpgradeSavedAddress('ws://custom-camera.local:8500/camera/preview') -eq 'ws://custom-camera.local:8500/camera/preview') 'Unrelated custom host preserved'