# Murmur tel qu'un ami le recoit : une archive, sur une machine vierge.
#
# Rien n'est installe ici — ni Python, ni bibliotheque Visual C++, ni modele.
# C'est le parcours complet : dezipper, lancer, laisser l'application aller
# chercher son modele, verifier qu'elle dicte.

$ErrorActionPreference = 'Continue'
$sortie = 'C:\resultat\rapport.txt'
$bureau = 'C:\Users\WDAGUtilityAccount\Desktop'
$appli = "$bureau\Murmur"

function Dire($texte) {
    Write-Host $texte
    Add-Content -Path $sortie -Value $texte -Encoding utf8
}

Set-Content -Path $sortie -Value "== Murmur, archive sur machine vierge ==" -Encoding utf8
Dire ("date          : " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Dire ("windows       : " + (Get-CimInstance Win32_OperatingSystem).Caption)
Dire ("carte video   : " + (Get-CimInstance Win32_VideoController |
                            Select-Object -First 1 -ExpandProperty Name))
Dire ("vulkan-1.dll  : " + (Test-Path "$env:WINDIR\System32\vulkan-1.dll"))

# -- 1. dezipper -------------------------------------------------------------
Dire ""
Dire "-- 1. l'archive --"
$zip = Get-ChildItem 'C:\murmur\dist\Murmur-*-windows-x64.zip' |
       Select-Object -First 1
if (-not $zip) { Dire "archive introuvable"; return }
Dire ("archive       : {0}  ({1:N0} Mo)" -f $zip.Name, ($zip.Length / 1MB))
Copy-Item $zip.FullName "$bureau\murmur.zip"
Expand-Archive "$bureau\murmur.zip" -DestinationPath $bureau -Force
Dire ("fichiers      : " + (Get-ChildItem $appli -Recurse -File).Count)
$modeles = Get-ChildItem $appli -Recurse -File |
           Where-Object { $_.Name -match '^ggml-(tiny|base|small|medium|large)' }
Dire ("modele dans l'archive : " + $(if ($modeles) { $modeles.Name } else { "aucun (attendu)" }))

# -- 2. premier lancement ----------------------------------------------------
Dire ""
Dire "-- 2. premier lancement --"
$app = Start-Process -FilePath "$appli\Murmur.exe" -PassThru
Dire "lance, attente du modele (jusqu'a 12 min)"

$dossierModeles = "$env:APPDATA\Murmur\modeles"
$obtenu = $null
foreach ($i in 1..72) {
    Start-Sleep -Seconds 10
    if (Test-Path $dossierModeles) {
        $fini = Get-ChildItem $dossierModeles -Filter '*.bin' -EA SilentlyContinue |
                Where-Object { $_.Name -notlike '*.partiel' }
        if ($fini) { $obtenu = $fini[0]; break }
        $encours = Get-ChildItem $dossierModeles -Filter '*.partiel' -EA SilentlyContinue
        if ($encours -and ($i % 6) -eq 0) {
            Dire ("  ... {0:N0} Mo recus" -f ($encours[0].Length / 1MB))
        }
    }
    if ($app.HasExited) { Dire "l'application s'est arretee"; break }
}

if ($obtenu) {
    Dire ("modele obtenu : {0}  ({1:N0} Mo)" -f $obtenu.Name, ($obtenu.Length / 1MB))
} else {
    Dire "aucun modele apres 12 min"
}

# -- 3. l'application dicte-t-elle ? -----------------------------------------
Dire ""
Dire "-- 3. en service --"
Start-Sleep -Seconds 40
$moteur = Get-Process -Name whisper-server -EA SilentlyContinue
Dire ("moteur        : " + $(if ($moteur) { "en marche" } else { "absent" }))

$code = @'
using System;
using System.Runtime.InteropServices;
public class RC {
  [DllImport("user32.dll", SetLastError=true)]
  public static extern bool RegisterHotKey(IntPtr h, int id, uint m, uint k);
  [DllImport("user32.dll")]
  public static extern bool UnregisterHotKey(IntPtr h, int id);
}
'@
Add-Type -TypeDefinition $code
$pris = -not [RC]::RegisterHotKey([IntPtr]::Zero, 1, 3, 0x44)
if (-not $pris) { [RC]::UnregisterHotKey([IntPtr]::Zero, 1) | Out-Null }
Dire ("ctrl+alt+d pris par Murmur : " + $pris)

# Une vraie transcription, sur un fichier fourni : c'est la seule preuve que
# la chaine complete fonctionne.
$conf = Get-Content "$env:APPDATA\Murmur\config.json" -Raw -EA SilentlyContinue |
        ConvertFrom-Json
if ($conf) {
    $port = $conf.moteur.port
    Dire ("modele retenu : " + $conf.moteur.modele)
    try {
        $wav = 'C:\murmur\spikes\t0_3_vad\parole_8s.wav'
        $debut = Get-Date
        $forme = @{ file = Get-Item $wav; language = 'fr'; response_format = 'json' }
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/inference" `
             -Method Post -Form $forme -TimeoutSec 120 -UseBasicParsing
        $ms = [int]((Get-Date) - $debut).TotalMilliseconds
        Dire ("transcription : $ms ms")
        Dire ("texte         : " + ($r.Content | ConvertFrom-Json).text.Trim())
    } catch {
        Dire ("transcription impossible : " + $_.Exception.Message)
    }
}

# -- 4. le tableau de bord ---------------------------------------------------
Dire ""
Dire "-- 4. tableau de bord --"
$tb = Start-Process -FilePath "$appli\Murmur.exe" -ArgumentList "--tableau","statistiques" -PassThru
Start-Sleep -Seconds 25
Dire ("il s'ouvre    : " + (-not $tb.HasExited))
if (-not $tb.HasExited) { Stop-Process -Id $tb.Id -Force -EA SilentlyContinue }

foreach ($nom in 'murmur.log', 'moteur.log') {
    $j = "$env:APPDATA\Murmur\logs\$nom"
    if (Test-Path $j) { Copy-Item $j "C:\resultat\$nom" -Force }
}
$log = "$env:APPDATA\Murmur\logs\murmur.log"
if (Test-Path $log) {
    Dire ""
    Dire "-- journal --"
    foreach ($l in (Get-Content $log -Tail 18)) { Dire ("  | " + $l) }
}

Dire ""
Dire "== fin =="
