# make-wtd-flight.ps1 - ONE command, full stickman video via Google Flow.
# Runs on the T470 (needs gflow-cli + SSH key to the VPS).
# Orchestrates: VPS(script) -> T470(Flow images) -> VPS(finish video).
#
#   & .\make-wtd-flight.ps1 "Why the sky is blue"
#   & .\make-wtd-flight.ps1 "Why the sky is blue" -Scenes 6 -Final
#     (scenes)   -Scenes N     storyboard scene count (default 5)
#     (optional) -Final        also assemble video (requires --no-audio off etc)
#     (optional) -Youtube      upload final video to YouTube (private)
#     (optional) -Private/-Public  privacy for the upload
#     (optional) -NoCheck      skip SSH connectivity precheck
#
# Requires: forked gflow-cli installed, gflow auth done once, SSH key to VPS.
param(
    [Parameter(Mandatory=$true)][string]$Topic,
    [int]$Scenes = 5,
    [switch]$Youtube,
    [string]$Privacy = "private",
    [switch]$SkipSshCheck
)

$ErrorActionPreference = "Stop"
$VPS = "root@167.233.41.251"
$VG  = "/root/ShortGPT/flow_pipeline"          # VPS working dir
$SLUG = ($Topic -replace '[^A-Za-z0-9]+','_').Trim('_').ToLower()
$LOCAL = "$env:USERPROFILE\flow_pipeline_$SLUG"
New-Item -ItemType Directory -Force -Path $LOCAL | Out-Null

# ------ SSH precheck ------
if (-not $SkipSshCheck) {
    Write-Host "[0] checking VPS SSH..."
    ssh $VPS "echo ok" | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "SSH to VPS failed." -ForegroundColor Red; exit 1 }
}

# ------ Step 1: generate storyboard + prompts on VPS ------
Write-Host "[1] VPS: generating storyboard + scene prompts..."
ssh $VPS "cd $VG && mkdir -p $SLUG && exit 0" 2>&1 | Out-Null
# run orchestrator in flow-staged so it writes flow_prompts.txt (no image gen yet)
ssh $VPS "cd $VG && source .venv/bin/activate 2>/dev/null; python orchestrator.py '$Topic' --flow-staged --scenes $Scenes --project-dir projects" 2>&1 | Select-Object -Last 20

# copy flow_prompts.txt down
Write-Host "[2] pulling scene prompts to T470..."
$sb = "$VG/projects/$SLUG/flow_prompts.txt"
scp "$VPS`:$sb" "$LOCAL\flow_prompts.txt"
if (-not (Test-Path "$LOCAL\flow_prompts.txt")) {
    Write-Host "No flow_prompts.txt produced - check VPS output above." -ForegroundColor Red; exit 1
}

# ------ Step 2: generate images on T470 through Google Flow ------
Write-Host "[3] T470: generating scenes via Google Flow (this is the slow step)..."
& powershell -File "$PSScriptRoot\flow-batch-gen.ps1" "$LOCAL\flow_prompts.txt" "$LOCAL\flow_out"

# ------ Step 3: push images back to VPS ------
Write-Host "[4] uploading Flow scenes to VPS..."
scp -r "$LOCAL\flow_out\*" "$VPS`:$VG/projects/$SLUG/flow_out/"

# ------ Step 4: finish on VPS (import images, TTS, assembly) ------
Write-Host "[5] VPS: assembling final video..."
$ytFlag = if ($Youtube) { " --youtube --privacy $Privacy" } else { "" }
ssh $VPS "cd $VG && source .venv/bin/activate 2>/dev/null; python orchestrator.py '$Topic' --flow-staged --scenes $Scenes --project-dir projects $ytFlag" 2>&1 | Select-Object -Last 25

Write-Host ""
Write-Host "=== Done: $Topic ==="  -ForegroundColor Green
Write-Host "VPS project: $VG/projects/$SLUG"  -ForegroundColor Cyan
if ($Youtube) { Write-Host "Uploaded to YouTube ($Privacy)." } else { Write-Host "Final video on VPS. Add -Youtube to upload." }