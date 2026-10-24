param([Parameter(Mandatory=$true)][string]$DatasetPath)
$ErrorActionPreference='Stop'
Add-Type -Path @((Join-Path $PSScriptRoot '../../Assets/MOSFETInspection/JetsonTestDataProtocol.cs'),(Join-Path $PSScriptRoot '../../Assets/MOSFETInspection/ElectricalSpec.cs'))
$options=[System.Text.Json.JsonSerializerOptions]::new();$options.IncludeFields=$true
$data=[System.Text.Json.JsonSerializer]::Deserialize([IO.File]::ReadAllText($DatasetPath),[JetsonTestDataProtocol+Dataset],$options)
[JetsonTestDataProtocol]::Validate($data)
function Check($value,$name){if(-not $value){throw $name};Write-Output ('PASS: '+$name)}
function Reject($action,$name){$rejected=$false;try{& $action}catch{$rejected=$true};Check $rejected $name}
Check ($data.rows.Length -eq 100) 'All 100 original CSV rows pass Unity protocol validation'
$normal=$data.rows|Where-Object id -eq B001
Check ([math]::Abs([JetsonTestDataProtocol]::Thickness(100,$normal)-100) -lt 0.0001) 'Baseline thickness is 100 nm'
$high=$data.rows|Where-Object id -eq B038
Check ([math]::Abs([JetsonTestDataProtocol]::Thickness(100,$high)-122.23) -lt 0.001) 'Oxide ratio is converted with explicit recipe target'
Check ([JetsonTestDataProtocol]::CanSelect($normal,'TCAD')) 'TCAD quartet selectable'
Check ([JetsonTestDataProtocol]::CanSelect($normal,'PC')) 'PC quartet selectable separately'
$predicted=$data.rows|Where-Object id -eq N001
Check (-not [JetsonTestDataProtocol]::CanSelect($predicted,'TCAD')) 'Missing TCAD values cannot silently use PC'
Check ([JetsonTestDataProtocol]::CanSelect($predicted,'PC')) 'Prediction-only row is usable as PC data'
$outside=$data.rows|Where-Object id -eq X001
Check (-not [JetsonTestDataProtocol]::CanSelect($outside,'TCAD') -and -not [JetsonTestDataProtocol]::CanSelect($outside,'PC')) 'Out-of-domain rows without electrical data remain view-only'
Check (-not [JetsonTestDataProtocol]::CanSelect($normal,'PC_HIGH')) 'Partial high precision columns cannot become a mixed quartet'
$normal.oxide_ratio=[float]::NaN
Reject {[JetsonTestDataProtocol]::Validate($data)} 'Non-finite knob rejected'
$normal.oxide_ratio=1
$data.rows[1].id=$normal.id
Reject {[JetsonTestDataProtocol]::Validate($data)} 'Duplicate sample ID rejected'
Write-Output 'JETSON_CSV_PROTOCOL_OK'
