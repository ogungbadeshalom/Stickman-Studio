# flow-batch-gen.ps1 - Generate MANY stickman scene images via Google Flow (migrated host).
# Reads one prompt per line from a file, generates each via your fixed gflow-cli fork,
# saves to an out folder, then uploads to the VPS.
#
# Usage:
#   & .\flow-batch-gen.ps1 -PromptFile prompts.txt -OutDir out
#   & .\flow-batch-gen.ps1 prompts.txt            # out defaults to ./flow_out
param(
    [Parameter(Mandatory=$true)][string]$PromptFile,
    [string]$OutDir = "flow_out"
)

$env:GFLOW_CLI_FLOW_HOST = "flow.google.com"
$PROJECT_ID = "ac5344ad-2704-4fe9-afbc-dad36e7e62c9"
$STYLE = "minimalist black line art stickman, simple round head, thin stick limbs, plain white background, no shading, clean vector style"

if (-not (Test-Path $PromptFile)) { Write-Host "No prompt file: $PromptFile" -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$prompts = Get-Content $PromptFile | Where-Object { $_.Trim() }
$i = 0
$ok = 0; $fail = 0
foreach ($p in $prompts) {
    $i++
    $full = "$p. $STYLE"
    $out = Join-Path $OutDir ("scene_{0:D3}.jpg" -f $i)
    Write-Host "[$i/$($prompts.Count)] $($p.Substring(0,[Math]::Min(50,$p.Length)))..."
    gflow image t2i $full --output $out --project $PROJECT_ID 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0 -and (Test-Path $out)) { $ok++ } else { $fail++ }
}
Write-Host ""; Write-Host "DONE: $ok generated, $fail failed, in $OutDir" -ForegroundColor Green

# optional sync back to VPS
$sync = Read-Host "Upload to VPS? (y/n)"
if ($sync -eq "y") {
    $VPS = "root@167.233.41.251"; $VG = "/root/flow_sync/queues"
    $batch = Read-Host "Batch folder name (e.g. vid1)"
    scp -r "$OutDir\*" "$VPS`:$VG/$batch/images/"
    Write-Host "Uploaded to VPS $VG/$batch/images" -ForegroundColor Green
}