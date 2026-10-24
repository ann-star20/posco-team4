param([Parameter(Mandatory=$true)][string]$DatasetPath)
$ErrorActionPreference='Stop'
$root=Join-Path $PSScriptRoot '../../Assets/MOSFETInspection'
if(-not ('JetsonTestDataProtocol' -as [type])){Add-Type -Path @((Join-Path $root 'JetsonTestDataProtocol.cs'),(Join-Path $root 'ElectricalSpec.cs'))}
if(-not ('IonDoseAssessment' -as [type])){Add-Type -Path (Join-Path $root 'IonDoseAssessment.cs')}
$options=[System.Text.Json.JsonSerializerOptions]::new();$options.IncludeFields=$true
$data=[System.Text.Json.JsonSerializer]::Deserialize([IO.File]::ReadAllText($DatasetPath),[JetsonTestDataProtocol+Dataset],$options)
function Check($ok,$message){if(!$ok){throw $message};'PASS: '+$message}
$sequence=[JetsonTestDataProtocol+AutoSequence]::new()
$normal=$sequence.BindIon($data,'TCAD','ion-wafer-1',7.7e12,7.315e12,8.085e12)
Check ($normal.category -eq 'normal' -and $normal.row.dose_ratio -eq 1 -and $normal.n_wafers -eq 1) 'Normal ion case comes from CSV'
$again=$sequence.BindIon($data,'PC','ion-wafer-1',8e12,7e12,9e12)
Check ($again.row.id -eq $normal.row.id -and $again.measurement_source -eq 'TCAD') 'Same wafer retains row and source'
$ng=$sequence.BindIon($data,'TCAD','ion-wafer-2',7.7e12,7.315e12,8.085e12)
$dose=[JetsonTestDataProtocol]::Dose(7.7e12,$ng.row)
Check ($ng.category -eq 'dose' -and [IonDoseAssessment]::Evaluate($dose,7.315e12,8.085e12,$true,$false) -eq 'FAIL') 'CSV ratio produces actual dose FAIL without changing target'
$electrical=$sequence.BindIon($data,'TCAD','ion-wafer-3',7.7e12,7.315e12,8.085e12)
Check ($electrical.category -eq 'electrical' -and [IonDoseAssessment]::Evaluate([JetsonTestDataProtocol]::Dose(7.7e12,$electrical.row),7.315e12,8.085e12,$true,$false) -eq 'OK' -and [ElectricalSpec]::Evaluate($electrical.Measurement.vth,$electrical.Measurement.bv) -eq [ElectricalSpec+Verdict]::NG) 'Dose OK and electrical NG remain separate'
$saved=$normal.row.dose_ratio;($data.rows|Where-Object id -eq $normal.row.id).dose_ratio=9
Check ($normal.row.dose_ratio -eq $saved) 'Bound dose survives later source edits'
$blocked=$false;try{[JetsonTestDataProtocol]::Dose(7.7e12,$null)|Out-Null}catch{$blocked=$true}
Check $blocked 'Missing CSV cannot fabricate a target measurement'
'ION_JETSON_CSV_SEQUENCE_OK (offline dataset fixture)'
