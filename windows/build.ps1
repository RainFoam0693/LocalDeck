$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python -c "from PIL import Image; Image.open('assets/LocalDeck.png').save('assets/LocalDeck.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
python windows/bundle_notices.py
if ($LASTEXITCODE -ne 0) { throw 'Dependency notices generation failed' }
$notices = (Resolve-Path build/third-party).Path
$icon = (Resolve-Path assets/LocalDeck.ico).Path
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LocalDeck --icon "$icon" --add-data "$icon;assets" --add-data "$notices;third-party" --hidden-import backend.windows_platform --hidden-import windows.terminal_session --exclude-module tkinter --exclude-module PySide6.QtNetwork --collect-all winpty --paths . --distpath dist/windows --workpath build/windows --specpath build windows/app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$package = 'dist/LocalDeck-1.0.1-Windows-x64'
New-Item -ItemType Directory -Force $package | Out-Null
Copy-Item dist/windows/LocalDeck.exe $package
Copy-Item windows/README.txt "$package/README.txt"
Copy-Item build/third-party "$package/third-party" -Recurse -Force
Compress-Archive -Path "$package/*" -DestinationPath "$package.zip" -Force
Copy-Item dist/windows/LocalDeck.exe dist/LocalDeck-1.0.1-Windows-x64.exe
$names = @('LocalDeck-1.0.1-Windows-x64.exe', 'LocalDeck-1.0.1-Windows-x64.zip')
$lines = foreach ($name in $names) {
    $hash = (Get-FileHash "dist/$name" -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $name"
}
[IO.File]::WriteAllLines((Join-Path $PWD 'dist/SHA256SUMS-Windows.txt'), $lines, [Text.UTF8Encoding]::new($false))
Write-Host 'Windows packages created in dist/'
