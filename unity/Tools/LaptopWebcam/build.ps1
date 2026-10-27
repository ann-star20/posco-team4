$ErrorActionPreference='Stop'
$python=Join-Path $PSScriptRoot '.build-env/Scripts/python.exe'
Push-Location $PSScriptRoot
try {
    $env:TCL_LIBRARY='.tcl/tcl8.6'
    $env:TK_LIBRARY='.tcl/tk8.6'
    & $python -m unittest -v test_webcam_sender.py
    if($LASTEXITCODE -ne 0){throw 'Webcam protocol tests failed.'}
    $tclData=(Join-Path $PSScriptRoot '.tcl/tcl8.6')+';_tcl_data'
    $tkData=(Join-Path $PSScriptRoot '.tcl/tk8.6')+';_tk_data'
    & $python -m PyInstaller --noconfirm --onefile --windowed --name AOI-Webcam --distpath release --workpath .build --specpath .build --hidden-import tkinter --add-data $tclData --add-data $tkData webcam_sender.py
    if($LASTEXITCODE -ne 0){throw 'EXE build failed.'}
    $exe=Join-Path $PSScriptRoot 'release/AOI-Webcam.exe'
    $report=Join-Path $PSScriptRoot 'exe-self-test.txt'
    if(Test-Path $report){Remove-Item -LiteralPath $report}
    $process=Start-Process -FilePath $exe -ArgumentList @('--self-test',('"'+$report+'"')) -PassThru -Wait -WindowStyle Hidden
    if($process.ExitCode -ne 0 -or -not (Test-Path $report)){throw 'Packaged EXE self-test failed.'}
    Get-Content $report
    Compress-Archive -Path 'release/AOI-Webcam.exe','release/사용방법.txt' -DestinationPath 'AOI-Laptop-Webcam.zip' -Force
} finally { Pop-Location }
