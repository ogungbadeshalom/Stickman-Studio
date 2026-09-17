# flow-gen.ps1 - Generate 1 image via Google Flow (migrated host), one command.
# Uses your fork's fixed gflow-cli (cookie fix) + your Flow project ID.
#
# Usage:
#   & .\flow-gen.ps1 "a minimalist black stickman pointing at a rising chart"
#   & .\flow-gen.ps1 "a stickman thinking" out.png
param(
    [Parameter(Mandatory=$true)][string]$Prompt,
    [string]$Out = "flow_output.jpg"
)

# --- your constants (edit once) ---
$env:GFLOW_CLI_FLOW_HOST = "flow.google.com"
$PROJECT_ID = "ac5344ad-2704-4fe9-afbc-dad36e7e62c9"
# consistent stickman style suffix for channel-wide uniformity
$STYLE = "minimalist black line art stickman, simple round head, thin stick limbs, plain white background, no shading, clean vector style"

$fullPrompt = "$Prompt. $STYLE"
Write-Host "[Flow] generating: $fullPrompt"
Write-Host "[Flow] output -> $Out"

gflow image t2i $fullPrompt --output $Out --project $PROJECT_ID
if ($LASTEXITCODE -eq 0 -and (Test-Path $Out)) {
    Write-Host "[OK] image saved: $Out" -ForegroundColor Green
} else {
    Write-Host "[FAIL] check gflow output above" -ForegroundColor Red
}