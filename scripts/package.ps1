$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force dist | Out-Null
$target = Join-Path (Get-Location) "dist\ArtifactScanAI.zip"
if (Test-Path $target) { Remove-Item $target -Force }
$exclude = @(".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "storage", "dist")
$items = Get-ChildItem -Force | Where-Object { $_.Name -notin $exclude }
Compress-Archive -Path $items.FullName -DestinationPath $target -CompressionLevel Optimal
Get-Item $target | Select-Object FullName, Length
Get-FileHash $target -Algorithm SHA256