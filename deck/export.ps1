# Render every slide to PNG with PowerPoint (for visual checks):  powershell -File export.ps1
$deck = Join-Path $PSScriptRoot "Data-Plumber-Hackathon.pptx"
$out = Join-Path $PSScriptRoot "qa"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
$pp = New-Object -ComObject PowerPoint.Application
try {
    $pres = $pp.Presentations.Open($deck, $true, $false, $false)
    $pres.Export($out, "PNG", 1600, 900)
    $pres.Close()
} finally {
    $pp.Quit()
}
Get-ChildItem $out | ForEach-Object { $_.FullName }
