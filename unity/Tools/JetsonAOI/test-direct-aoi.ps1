$ErrorActionPreference = 'Stop'
$endpoint = 'ws://192.168.213.167:8400/aoi'
$logDirectory = Join-Path $PSScriptRoot 'DirectTestResults'
$socket = $null
$secret = $null
$token = $null
$pointer = [IntPtr]::Zero
$pendingImage = $null
$report = [ordered]@{
    endpoint = $endpoint
    started_at = [DateTimeOffset]::Now.ToString('o')
    source = 'fixture_request_from_pc_not_unity'
    request_sent = $false
    responses = @()
    status = 'starting'
}
try {
    Write-Host ('AOI fixture test: ' + $endpoint)
    Write-Host 'Enter the AOI_UNITY_TOKEN provided by your teammate. Input is hidden.'
    $secret = Read-Host 'AOI_UNITY_TOKEN' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($token)) { throw 'Token is empty. No request was sent.' }
    $request = [ordered]@{
        type = 'aoi.inspection.requested'
        schema_version = 1
        request_id = [guid]::NewGuid().ToString()
        job_id = [guid]::NewGuid().ToString()
        run_id = [guid]::NewGuid().ToString()
        lot_id = 'LOT-UNITY-TEST-001'
        unit_id = 'MOSFET-TEST-001'
        attempt = 1
        fixture_name = 'test_aoi_mosfet1.jpg'
        api_token = $token
    }
    $report.request_id = $request.request_id
    $report.job_id = $request.job_id
    $report.run_id = $request.run_id
    $socket = New-Object System.Net.WebSockets.ClientWebSocket
    $socket.Options.Proxy = $null
    $connectTimeout = New-Object System.Threading.CancellationTokenSource
    $connectTimeout.CancelAfter(8000)
    try { $null = $socket.ConnectAsync([Uri]$endpoint, $connectTimeout.Token).GetAwaiter().GetResult() }
    finally { $connectTimeout.Dispose() }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($request | ConvertTo-Json -Compress))
    $segment = New-Object 'System.ArraySegment[byte]' -ArgumentList @(,$bytes)
    $sendTimeout = New-Object System.Threading.CancellationTokenSource
    $sendTimeout.CancelAfter(8000)
    try { $null = $socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $sendTimeout.Token).GetAwaiter().GetResult() }
    finally { $sendTimeout.Dispose(); [Array]::Clear($bytes, 0, $bytes.Length); $request.api_token = $null }
    $report.request_sent = $true
    Write-Host ('Request sent: ' + $report.request_id)
    Write-Host 'Waiting up to 60 seconds for responses. Do not close this window.'
    $receiveTimeout = New-Object System.Threading.CancellationTokenSource
    $receiveTimeout.CancelAfter(60000)
    try {
        while ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            $stream = New-Object IO.MemoryStream
            $messageType = $null
            try {
                do {
                    $buffer = New-Object byte[] 16384
                    $chunk = New-Object 'System.ArraySegment[byte]' -ArgumentList @(,$buffer)
                    $received = $socket.ReceiveAsync($chunk, $receiveTimeout.Token).GetAwaiter().GetResult()
                    if ($received.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) { break }
                    if ($null -eq $messageType) { $messageType = $received.MessageType }
                    if ($messageType -ne $received.MessageType) { throw 'Message type changed between fragments.' }
                    $stream.Write($buffer, 0, $received.Count)
                    if ($stream.Length -gt 16777216) { throw 'Response exceeded 16 MiB limit.' }
                } while (-not $received.EndOfMessage)
                if ($received.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) { break }
                if ($messageType -eq [System.Net.WebSockets.WebSocketMessageType]::Binary) {
                    if ($null -eq $pendingImage) { throw 'Image arrived without matching result metadata.' }
                    $photo = $stream.ToArray()
                    if ($photo.Length -ne [long]$pendingImage.byte_length) { throw 'Image byte length does not match metadata.' }
                    $hasher = [Security.Cryptography.SHA256]::Create()
                    try { $hash = [BitConverter]::ToString($hasher.ComputeHash($photo)).Replace('-', '').ToLowerInvariant() }
                    finally { $hasher.Dispose() }
                    if ($hash -ne $pendingImage.sha256) { throw 'Image SHA256 does not match metadata.' }
                    if ($photo.Length -lt 4 -or $photo[0] -ne 255 -or $photo[1] -ne 216 -or $photo[2] -ne 255 -or $photo[-2] -ne 255 -or $photo[-1] -ne 217) { throw 'Image is not a complete JPEG.' }
                    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
                    $imagePath = Join-Path $logDirectory ('aoi-' + $report.request_id + '.jpg')
                    [IO.File]::WriteAllBytes($imagePath, $photo)
                    $report.image_path = $imagePath
                    $report.image_sha256 = $hash
                    $report.status = 'result_and_image_received'
                    $pendingImage = $null
                    Write-Host ('Image saved and verified: ' + $imagePath) -ForegroundColor Green
                    break
                }
                if ($null -ne $pendingImage) { throw 'Expected image binary frame after result metadata.' }
                $utf8 = New-Object Text.UTF8Encoding($false, $true)
                $responseText = $utf8.GetString($stream.ToArray()).Replace($token, '[REDACTED]')
                $report.responses += $responseText
                Write-Host $responseText
                $report.status = 'response_received'
                $response = $responseText | ConvertFrom-Json
                if ($response.type -eq 'aoi.inspection.failed') {
                    $report.status = 'inspection_failed'
                    break
                }
                if ($response.type -eq 'aoi.inspection.completed') {
                    foreach ($field in @('request_id','job_id','run_id','lot_id','unit_id','attempt')) {
                        if ([string]$response.$field -cne [string]$request[$field]) { throw ('Response does not match request: ' + $field) }
                    }
                    $report.result_origin = $response.result_origin
                    if ($response.image.binary_frame_follows -eq $true -or $response.binary_frame_follows -eq $true) {
                        $pendingImage = $response.image
                        if ($null -eq $pendingImage -or $pendingImage.mime_type -ne 'image/jpeg' -or [long]$pendingImage.byte_length -le 0 -or [long]$pendingImage.byte_length -gt 16777216 -or $pendingImage.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid image metadata.' }
                        $report.status = 'image_pending'
                    } else { break }
                }
                if ($report.responses.Count -ge 16) { break }
            } finally { $stream.Dispose() }
        }
    } catch {
        if (-not $receiveTimeout.IsCancellationRequested) { throw }
        if ($report.responses.Count -eq 0) { $report.status = 'sent_but_no_response_within_60_seconds' }
    } finally { $receiveTimeout.Dispose() }
    if ($null -ne $pendingImage) { throw 'Result received, but image transfer did not complete.' }
    if ($report.status -eq 'starting') { $report.status = 'server_closed_without_response' }
} catch {
    $report.status = 'failed'
    $message = $_.Exception.Message
    if (-not [string]::IsNullOrEmpty($token)) { $message = $message.Replace($token, '[REDACTED]') }
    $report.error = $message
    Write-Host ('Error: ' + $message) -ForegroundColor Red
} finally {
    if ($socket) { $socket.Dispose() }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    if ($secret) { $secret.Dispose() }
    $token = $null
    $report.finished_at = [DateTimeOffset]::Now.ToString('o')
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $logPath = Join-Path $logDirectory ('aoi-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $logPath -Encoding UTF8
    Write-Host ('Status: ' + $report.status)
    Write-Host ('Sanitized result saved: ' + $logPath)
    Read-Host 'Press Enter to close' | Out-Null
}
