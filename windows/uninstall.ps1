# Quita Post-its (las notas guardadas en %APPDATA%\PostIts se conservan).
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*postits.pyw*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
foreach ($folder in [Environment]::GetFolderPath("Startup"), [Environment]::GetFolderPath("Programs")) {
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $folder "Post-its.lnk")
}
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $env:LOCALAPPDATA "PostIts")
Write-Host "Post-its desinstalado."
