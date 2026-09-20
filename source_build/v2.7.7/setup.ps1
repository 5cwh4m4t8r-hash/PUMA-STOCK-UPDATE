$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$log = Join-Path $root 'install_log.txt'
if (Test-Path $log) { Remove-Item $log -Force }
Start-Transcript -Path $log -Force | Out-Null

function Stop-WithMessage([string]$msg) {
    Write-Host ""
    Write-Host "[오류] $msg" -ForegroundColor Red
    Write-Host "설치 기록: $log" -ForegroundColor Yellow
    Stop-Transcript | Out-Null
    Read-Host "Enter를 누르면 창이 닫힙니다"
    exit 1
}

try {
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host " PUMA STOCK PRO v0.6 - 자동 설치" -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1/5 Python 3.11 찾는 중..."

    $python = $null
    $known = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )
    foreach ($p in $known) {
        if (Test-Path $p) { $python = $p; break }
    }

    if (-not $python) {
        $py = Get-Command py -ErrorAction SilentlyContinue
        if ($py) {
            try {
                $resolved = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1).Trim()
                if ($resolved -and (Test-Path $resolved)) { $python = $resolved }
            } catch {}
        }
    }

    if (-not $python) {
        $pc = Get-Command python -ErrorAction SilentlyContinue
        if ($pc) { $python = $pc.Source }
    }

    if (-not $python) {
        Stop-WithMessage "Python을 찾지 못했습니다. Python 3.11(64비트)을 설치한 뒤 다시 실행해 주세요."
    }

    $ver = (& $python -c "import sys,platform; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor)); print(platform.architecture()[0])")
    Write-Host "   발견: $python" -ForegroundColor Green
    Write-Host "   Python $($ver[0]) / $($ver[1])" -ForegroundColor Green

    Write-Host "2/5 PUMA 전용 실행환경 만드는 중..."
    $venv = Join-Path $root '.venv'
    $venvPy = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $venvPy)) {
        & $python -m venv $venv
        if ($LASTEXITCODE -ne 0) { Stop-WithMessage "가상환경 생성에 실패했습니다." }
    }

    Write-Host "3/5 설치도구 준비 중..."
    & $venvPy -m ensurepip --upgrade
    & $venvPy -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "pip 준비에 실패했습니다." }

    Write-Host "4/5 PUMA에 필요한 패키지 설치 중... (처음에는 몇 분 걸릴 수 있습니다)"
    & $venvPy -m pip install --prefer-binary -r (Join-Path $root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "필수 패키지 설치에 실패했습니다. 인터넷 연결을 확인해 주세요." }

    Write-Host "5/5 설치 검사 중..."
    & $venvPy -c "import PySide6, requests, websockets; print('PUMA dependency check: OK')"
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "설치 검사를 통과하지 못했습니다." }

    "installed $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`npython=$python" | Set-Content -Path (Join-Path $root 'INSTALL_OK.txt') -Encoding UTF8
    Write-Host ""
    Write-Host "===============================================" -ForegroundColor Green
    Write-Host " 설치 완료!" -ForegroundColor Green
    Write-Host " 이제 2_START_PUMA.vbs 를 더블클릭하면 됩니다." -ForegroundColor Green
    Write-Host "===============================================" -ForegroundColor Green
    Stop-Transcript | Out-Null
    Read-Host "Enter를 누르면 설치창이 닫힙니다"
    exit 0
}
catch {
    try { Write-Host $_.Exception.ToString() -ForegroundColor Red } catch {}
    Stop-WithMessage "예상하지 못한 설치 오류가 발생했습니다."
}
