function Select-TeamJetsonHostKey {
    param([string[]]$Lines,[string]$TargetHost='192.168.213.167')
    # Fingerprint independently confirmed by the user and teammate in this session.
    $expected='SHA256:lkwd/1cRaXTgOeZhTzgGhYn+7AioZsA4XgjxcdjCwkk'
    foreach($line in $Lines){
        if($line -notmatch ('^'+[regex]::Escape($TargetHost)+'\s+ssh-ed25519\s+([A-Za-z0-9+/=]+)\s*$')){continue}
        $encoded=$Matches[1]
        try{$bytes=[Convert]::FromBase64String($encoded)}catch{continue}
        $sha=[Security.Cryptography.SHA256]::Create()
        try{$fingerprint='SHA256:'+([Convert]::ToBase64String($sha.ComputeHash($bytes)).TrimEnd('='))}finally{$sha.Dispose()}
        if($fingerprint -ceq $expected){return $line.Trim()}
    }
    throw 'Jetson host key does not match the fingerprint confirmed by your teammate. Connection stopped.'
}
