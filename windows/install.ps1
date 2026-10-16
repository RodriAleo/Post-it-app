# Instala Post-its para el usuario actual y lo arranca al iniciar sesión.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dest = Join-Path $env:LOCALAPPDATA "PostIts\app"

# Python 3 con Tkinter (el instalador de python.org lo trae por defecto)
$pythonw = $null
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $exe = & py.exe -3 -c "import sys, tkinter; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $exe) { $pythonw = Join-Path (Split-Path $exe) "pythonw.exe" }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") { $pythonw = $cmd.Source }
}
if (-not $pythonw -or -not (Test-Path $pythonw)) {
    Write-Host "No encontré Python 3. Instalalo desde https://www.python.org/downloads/ y volvé a correr este instalador." -ForegroundColor Red
    exit 1
}

# cerrar una instancia anterior
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*postits.pyw*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

New-Item -ItemType Directory -Force -Path $dest | Out-Null
foreach ($dir in "common", "windows") {
    $target = Join-Path $dest $dir
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse (Join-Path $repo $dir) $target
}

$script = Join-Path $dest "windows\postits.pyw"
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in [Environment]::GetFolderPath("Startup"), [Environment]::GetFolderPath("Programs")) {
    $lnk = $shell.CreateShortcut((Join-Path $folder "Post-its.lnk"))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = "`"$script`""
    $lnk.WorkingDirectory = $dest
    $lnk.Description = "Notas adhesivas en el escritorio (abrirlo de nuevo crea una nota)"
    $lnk.Save()
}

Start-Process -FilePath $pythonw -ArgumentList "`"$script`""
Write-Host "Post-its instalado. Notas en $env:APPDATA\PostIts\notes.json" -ForegroundColor Green
