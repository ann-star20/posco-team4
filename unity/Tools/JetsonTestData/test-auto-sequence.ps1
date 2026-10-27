param([Parameter(Mandatory=$true)][string]$DatasetPath)
$ErrorActionPreference='Stop'
$root=Join-Path $PSScriptRoot '../../Assets/MOSFETInspection'
Add-Type -Path @((Join-Path $root 'JetsonTestDataProtocol.cs'),(Join-Path $root 'ElectricalSpec.cs'))
$options=[System.Text.Json.JsonSerializerOptions]::new();$options.IncludeFields=$true
$data=[System.Text.Json.JsonSerializer]::Deserialize([IO.File]::ReadAllText($DatasetPath),[JetsonTestDataProtocol+Dataset],$options)
function Check($value,$name){if(-not $value){throw $name};Write-Output ('PASS: '+$name)}
$sequence=[JetsonTestDataProtocol+AutoSequence]::new()
$normal=$sequence.Bind($data,'TCAD','wafer-1',100,95,105,1)
Check ($normal.automatic -and $normal.category -eq 'normal' -and $normal.row.id -eq 'B001') 'First new wafer receives a normal row'
$again=$sequence.Bind($data,'PC','wafer-1',200,190,210,25)
Check ($again.row.id -eq $normal.row.id -and $again.measurement_source -eq 'TCAD' -and $again.n_wafers -eq 1 -and $again.reference_target_nm -eq 100) 'Same wafer retains its row, source, count and thickness reference on reinspection'
$high=$sequence.Bind($data,'TCAD','wafer-2',100,95,105,1)
Check ($high.category -eq 'thickness' -and ($high.row.oxide_ratio -lt .95 -or $high.row.oxide_ratio -gt 1.05)) 'Second new wafer receives a thickness deviation'
$electric=$sequence.Bind($data,'TCAD','wafer-3',100,95,105,1)
Check ($electric.category -eq 'electrical' -and $electric.row.oxide_ratio -ge .95 -and $electric.row.oxide_ratio -le 1.05 -and [ElectricalSpec]::Evaluate($electric.Measurement.vth,$electric.Measurement.bv) -eq [ElectricalSpec+Verdict]::NG) 'Third new wafer passes thickness and fails electrical limits'
$next=$sequence.Bind($data,'PC','wafer-4',100,95,105,1)
Check ($next.category -eq 'normal' -and $next.measurement_source -eq 'PC') 'Sequence wraps and uses selected source for new wafers'
$saved=$normal.row.tcad.vth
($data.rows|Where-Object id -eq B001).tcad.vth=99
Check ($normal.row.tcad.vth -eq $saved) 'Bound row is a snapshot independent of later dataset edits'
Check ($normal.Label.Contains('CSV') -and $normal.Label.Contains('자동')) 'Automatic provenance appears in result label'
$data.rows=@($data.rows|Where-Object id -eq B001)
$missing=[JetsonTestDataProtocol+AutoSequence]::new();$blocked=$false
try{$missing.Bind($data,'TCAD','incomplete',100,95,105,1)|Out-Null}catch{$blocked=$true}
Check $blocked 'Incomplete category set is blocked instead of inventing outcomes'
Write-Output 'JETSON_CSV_AUTO_OK'
