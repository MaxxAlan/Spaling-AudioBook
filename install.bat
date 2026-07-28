@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Spaling Audiobook Installer

set "ROOT=%CD%"
set "POSTER_DIR=%ROOT%\poster-generator"
set "VENV_DIR=%ROOT%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "OLLAMA_LOG=%TEMP%\spaling-ollama.log"
set "COMFYUI_COMMIT=806e092ed42772e4ce7abf44c97c50021cc4bd10"
set "IPADAPTER_COMMIT=a0f451a5113cf9becb0847b92884cb10cbdec0ef"
set "DREAMSHAPER_SHA256=879DB523C30D3B9017143D56705015E15A2CB5628762C11D086FED9538ABD7FD"
set "REALISTIC_VISION_SHA256=C48BFD159CD7A6507B128685E963C398FA72399CEFAFAF603781DF50CE836CC7"

echo.
echo ================================================================
echo              SPALING AUDIOBOOK INSTALLER
echo ================================================================
echo Thu muc cai dat: %ROOT%
echo.

for /f %%G in ('powershell -NoProfile -Command "[math]::Floor((Get-PSDrive -Name ([IO.Path]::GetPathRoot('%ROOT%').Substring(0,1))).Free/1GB)"') do set "FREE_GB=%%G"
if %FREE_GB% LSS 35 (
    echo [LOI] Can toi thieu 35 GB trong. Hien con %FREE_GB% GB.
    goto :FAIL
)

:: ================================================================
:: STEP 1: KIEM TRA WINGET
:: ================================================================

echo [1/7] Dang kiem tra Windows Package Manager...

where winget >nul 2>&1
if errorlevel 1 (
    echo [THIEU] Dang bootstrap Windows Package Manager...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\tools\bootstrap_winget.ps1"
    if errorlevel 1 (
        echo [LOI] Khong the cai WinGet. Windows co the bi policy chan cai phan mem.
        goto :FAIL
    )
    call :REFRESH_PATH
)

where winget >nul 2>&1
if errorlevel 1 (
    echo [LOI] WinGet da duoc cai nhung chua xuat hien trong PATH.
    goto :FAIL
)

echo [OK] WinGet san sang.

where git >nul 2>&1
if errorlevel 1 (
    echo [THIEU] Dang cai Git...
    winget install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements
    if errorlevel 1 goto :FAIL
    call :REFRESH_PATH
)

where git >nul 2>&1
if errorlevel 1 (
    echo [LOI] Git da duoc cai nhung CMD chua tim thay git.exe.
    goto :FAIL
)


:: ================================================================
:: STEP 2: NODE.JS
:: ================================================================

echo.
echo [2/7] Dang kiem tra Node.js va npm...

where node >nul 2>&1
if not errorlevel 1 node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)" >nul 2>&1
if errorlevel 1 (
    echo [THIEU] Dang cai/cap nhat Node.js LTS 20+...

    winget install ^
        --id OpenJS.NodeJS.LTS ^
        -e ^
        --force ^
        --silent ^
        --accept-source-agreements ^
        --accept-package-agreements

    if errorlevel 1 (
        echo [LOI] Khong the cai Node.js.
        goto :FAIL
    )

    call :REFRESH_PATH
)

where node >nul 2>&1
if errorlevel 1 (
    echo [LOI] Node.js da duoc cai nhung CMD chua tim thay node.exe.
    echo Hay dong installer, mo lai CMD va chay lai.
    goto :FAIL
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay npm sau khi cai Node.js.
    goto :FAIL
)

for /f "tokens=*" %%V in ('node --version') do echo [OK] Node.js %%V
for /f "tokens=*" %%V in ('npm --version') do echo [OK] npm %%V


:: ================================================================
:: STEP 3: PYTHON, FFMPEG, OLLAMA
:: ================================================================

echo.
echo [3/7] Dang kiem tra Python, FFmpeg va Ollama...

call :DETECT_PYTHON

if not defined PYTHON_CMD (
    echo [THIEU] Dang cai Python 3.11...

    winget install ^
        --id Python.Python.3.11 ^
        -e ^
        --silent ^
        --accept-source-agreements ^
        --accept-package-agreements

    if errorlevel 1 (
        echo [LOI] Khong the cai Python 3.11.
        goto :FAIL
    )

    call :REFRESH_PATH
    call :DETECT_PYTHON
)

if not defined PYTHON_CMD (
    echo [LOI] Python da duoc cai nhung installer khong tim thay.
    echo Hay dong CMD, mo lai va chay installer lan nua.
    goto :FAIL
)

echo [OK] Python command: %PYTHON_CMD%

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [THIEU] Dang cai FFmpeg...

    winget install ^
        --id Gyan.FFmpeg ^
        -e ^
        --silent ^
        --accept-source-agreements ^
        --accept-package-agreements

    if errorlevel 1 (
        echo [LOI] Khong the cai FFmpeg.
        goto :FAIL
    )

    call :REFRESH_PATH
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [LOI] FFmpeg da duoc cai nhung installer khong tim thay.
    echo Hay dong CMD, mo lai va chay installer lan nua.
    goto :FAIL
)

echo [OK] FFmpeg san sang.

where nvidia-smi >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%V in ('nvidia-smi --query-gpu=driver_version --format=csv^,noheader 2^>nul') do echo [*] NVIDIA driver: %%V
    ffmpeg -hide_banner -loglevel error -f lavfi -i color=size=128x128:duration=0.1 -frames:v 1 -an -c:v h264_nvenc -f null NUL >nul 2>&1
    if errorlevel 1 (
        echo [CANH BAO] NVENC co ten trong FFmpeg nhung khong khoi tao duoc.
        echo             Hay cap nhat driver tai https://www.nvidia.com/Download/index.aspx
        echo             Ung dung se tu dong dung CPU libx264 de job van hoan thanh.
    ) else (
        echo [OK] GPU NVENC encode da duoc xac minh bang mot frame thuc.
    )
) else (
    echo [CANH BAO] Khong tim thay nvidia-smi. Video se fallback sang CPU libx264.
)

where ollama >nul 2>&1
if errorlevel 1 (
    echo [THIEU] Dang cai Ollama...

    winget install ^
        --id Ollama.Ollama ^
        -e ^
        --silent ^
        --accept-source-agreements ^
        --accept-package-agreements

    if errorlevel 1 (
        echo [LOI] Khong the cai Ollama.
        goto :FAIL
    )

    call :REFRESH_PATH
)

where ollama >nul 2>&1
if errorlevel 1 (
    echo [LOI] Ollama da duoc cai nhung installer khong tim thay.
    echo Hay dong CMD, mo lai va chay installer lan nua.
    goto :FAIL
)

echo [OK] Ollama san sang.


:: ================================================================
:: STEP 4: TAO PYTHON VIRTUAL ENVIRONMENT VA CAI PNPM
:: ================================================================

echo.
echo [4/7] Dang chuan bi moi truong Python va Node.js...

if not exist "%ROOT%\requirements.txt" (
    echo [LOI] Khong tim thay:
    echo       %ROOT%\requirements.txt
    goto :FAIL
)

if not exist "%POSTER_DIR%\" (
    echo [LOI] Khong tim thay thu muc:
    echo       %POSTER_DIR%
    goto :FAIL
)

if not exist "%ROOT%\audiobook.py" (
    echo [LOI] Khong tim thay:
    echo       %ROOT%\audiobook.py
    goto :FAIL
)

:: Tao lai venv neu no duoc tao bang sai phien ban Python
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [*] Venv cu khong dung Python 3.11, dang tao lai...
        rmdir /s /q "%VENV_DIR%"
    )
)

:: Tao Python venv
if not exist "%VENV_PYTHON%" (
    echo [*] Dang tao Python virtual environment...

    %PYTHON_CMD% -m venv "%VENV_DIR%"

    if errorlevel 1 (
        echo [LOI] Khong the tao virtual environment.
        goto :FAIL
    )

    echo [OK] Da tao venv: %VENV_DIR%
) else (
    echo [OK] Virtual environment da ton tai.
)

:: Kich hoat venv va cai dependencies
echo [*] Dang kich hoat venv va cap nhat pip...
call "%VENV_DIR%\Scripts\activate.bat"
"%VENV_PYTHON%" -m pip install --upgrade pip setuptools wheel

if errorlevel 1 (
    echo [LOI] Khong the cap nhat pip.
    goto :FAIL
)

echo [*] Dang cai Python dependencies...
"%VENV_PYTHON%" -m pip install -r "%ROOT%\requirements.txt" pytest huggingface_hub

if errorlevel 1 (
    echo [LOI] Cai Python dependencies that bai.
    goto :FAIL
)

echo [*] Dang tai local ASR model de kiem duyet noi dung TTS offline...
"%VENV_PYTHON%" -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('[OK] faster-whisper small da san sang offline')"
if errorlevel 1 (
    echo [LOI] Khong the tai model faster-whisper small cho TTS semantic QA.
    goto :FAIL
)

:: Cai pnpm (chi can 1 lan, dung local)
where pnpm >nul 2>&1
if errorlevel 1 (
    echo [THIEU] Dang cai pnpm...

    call npm install --global pnpm@11.9.0

    if errorlevel 1 (
        echo [LOI] Khong the cai pnpm.
        goto :FAIL
    )

    call :REFRESH_PATH
)

where pnpm >nul 2>&1
if errorlevel 1 (
    echo [LOI] pnpm da duoc cai nhung CMD chua tim thay.
    echo Hay dong installer, mo lai CMD va chay lai.
    goto :FAIL
)

for /f "tokens=*" %%V in ('pnpm --version') do echo [OK] pnpm %%V


:: ================================================================
:: STEP 5: COMFYUI VA IMAGE MODELS
:: ================================================================

echo.
echo [5/7] Dang cai ComfyUI va Image Models...

:: Dam bao venv dang kich hoat
call "%VENV_DIR%\Scripts\activate.bat"

set "COMFYUI_DIR=%ROOT%\ComfyUI"
set "COMFYUI_MODELS=%COMFYUI_DIR%\models\checkpoints"
set "IPADAPTER_NODE=%COMFYUI_DIR%\custom_nodes\ComfyUI_IPAdapter_plus"
set "IPADAPTER_MODELS=%COMFYUI_DIR%\models\ipadapter"
set "CLIP_VISION_MODELS=%COMFYUI_DIR%\models\clip_vision"

if not exist "%COMFYUI_DIR%" (
    echo [*] Dang clone ComfyUI...
    git clone https://github.com/comfyanonymous/ComfyUI.git "%COMFYUI_DIR%"

    if errorlevel 1 (
        echo [LOI] Khong the clone ComfyUI.
        goto :FAIL
    )
) else (
    echo [OK] ComfyUI da ton tai.
)

echo [*] Dang khoa ComfyUI tai ban da kiem thu %COMFYUI_COMMIT%...
git -C "%COMFYUI_DIR%" fetch --depth 1 origin %COMFYUI_COMMIT%
if errorlevel 1 goto :FAIL
git -C "%COMFYUI_DIR%" checkout --detach %COMFYUI_COMMIT%
if errorlevel 1 goto :FAIL

echo [*] Dang kiem tra PyTorch CUDA...
"%VENV_PYTHON%" -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if errorlevel 1 (
    echo [*] Dang cai PyTorch CUDA...
    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    if errorlevel 1 (
        echo [LOI] Cai PyTorch CUDA that bai.
        goto :FAIL
    )
) else (
    echo [OK] PyTorch CUDA da san sang.
)

"%VENV_PYTHON%" -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if errorlevel 1 (
    echo [LOI] PyTorch khong nhan GPU CUDA.
    goto :FAIL
)

echo [*] Dang cai ComfyUI dependencies (trong venv)...
"%VENV_PYTHON%" -m pip install -r "%COMFYUI_DIR%\requirements.txt" -q
if errorlevel 1 (
    echo [LOI] Cai ComfyUI dependencies that bai.
    goto :FAIL
)

if not exist "%COMFYUI_MODELS%" mkdir "%COMFYUI_MODELS%"

if not exist "%IPADAPTER_NODE%\.git" (
    echo [*] Dang cai IP-Adapter Plus cho continuity nhan vat...
    git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git "%IPADAPTER_NODE%"
    if errorlevel 1 goto :FAIL
)
git -C "%IPADAPTER_NODE%" fetch --depth 1 origin %IPADAPTER_COMMIT%
if errorlevel 1 goto :FAIL
git -C "%IPADAPTER_NODE%" checkout --detach %IPADAPTER_COMMIT%
if errorlevel 1 goto :FAIL
if exist "%IPADAPTER_NODE%\requirements.txt" (
    "%VENV_PYTHON%" -m pip install -r "%IPADAPTER_NODE%\requirements.txt" -q
    if errorlevel 1 goto :FAIL
)
if not exist "%IPADAPTER_MODELS%" mkdir "%IPADAPTER_MODELS%"
if not exist "%CLIP_VISION_MODELS%" mkdir "%CLIP_VISION_MODELS%"
"%VENV_PYTHON%" "%ROOT%\tools\download_image_models.py" --identity
if errorlevel 1 goto :FAIL
echo [OK] IP-Adapter SD1.5 da san sang; InstantID/SDXL khong bat mac dinh tren GPU VRAM thap.

echo [*] Dang tai DreamShaper 8 model...
"%VENV_PYTHON%" -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='Lykon/DreamShaper', filename='DreamShaper_8_pruned.safetensors', local_dir='%COMFYUI_MODELS%')"

if errorlevel 1 (
    echo [LOI] Tai DreamShaper that bai.
    goto :FAIL
) else (
    echo [OK] DreamShaper 8 da san sang.
)

echo [*] Dang tai Realistic Vision 6 (SD1.5, low-VRAM)...
"%VENV_PYTHON%" -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='SG161222/Realistic_Vision_V6.0_B1_noVAE', filename='Realistic_Vision_V6.0_NV_B1_fp16.safetensors', local_dir='%COMFYUI_MODELS%')"

if errorlevel 1 (
    echo [LOI] Tai Realistic Vision that bai.
    goto :FAIL
) else (
    echo [OK] Realistic Vision da san sang.
)


:: ================================================================
:: STEP 6: CAU HINH TEXT AI MODELS
:: ================================================================

echo.
echo [6/7] Dang cau hinh Text AI Models...

if not exist "%POSTER_DIR%\.env" (
    if exist "%POSTER_DIR%\.env.example" (
        echo [*] Dang tao .env tu .env.example...
        copy /y "%POSTER_DIR%\.env.example" "%POSTER_DIR%\.env" >nul
    )
)

echo [*] Dang cau hinh Ollama va ComfyUI local...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%POSTER_DIR%\.env'; $c=if(Test-Path -LiteralPath $p){Get-Content -LiteralPath $p -Raw}else{''}; $m=[ordered]@{TEXT_AI_PROVIDER='ollama';TEXT_AI_MODEL='qwen2.5:7b';OLLAMA_BASE_URL='http://127.0.0.1:11434';VISION_QA_MODEL='moondream';VISION_QA_JUDGE_MODEL='qwen2.5:1.5b';IMAGE_AI_PROVIDER='comfyui';COMFYUI_BASE_URL='http://127.0.0.1:8188';COMFYUI_PATH='%COMFYUI_DIR%';COMFYUI_WORKFLOW='%POSTER_DIR%\workflows\sd15_basic.json';COMFYUI_PYTHON='%VENV_PYTHON%'}; foreach($k in $m.Keys){$line=$k+'='+$m[$k]; if($c -match ('(?m)^'+[regex]::Escape($k)+'=.*$')){$c=[regex]::Replace($c,('(?m)^'+[regex]::Escape($k)+'=.*$'),$line)}else{$c=$c.TrimEnd()+[Environment]::NewLine+$line+[Environment]::NewLine}}; Set-Content -LiteralPath $p -Value $c -Encoding utf8"
if errorlevel 1 (
    echo [LOI] Khong the cau hinh poster-generator\.env.
    goto :FAIL
)

call :ENSURE_OLLAMA

if errorlevel 1 (
    echo [LOI] Ollama server khong khoi dong duoc.
    echo Log: %OLLAMA_LOG%
    goto :FAIL
)

echo [*] Dang tai Text AI Models...
echo   - qwen2.5:1.5b (narration guidance)
echo   - qwen2.5:7b (story prompts)
echo   - moondream (storyboard visual QA, CPU low-VRAM)

ollama pull qwen2.5:1.5b
if errorlevel 1 (
    echo [LOI] Tai qwen2.5:1.5b that bai.
    goto :FAIL
)

ollama pull qwen2.5:7b
if errorlevel 1 (
    echo [LOI] Tai qwen2.5:7b that bai.
    goto :FAIL
)

ollama pull moondream
if errorlevel 1 (
    echo [LOI] Tai moondream visual QA model that bai.
    goto :FAIL
)

echo [OK] AI Models da san sang.


:: ================================================================
:: STEP 7: BUILD FRONTEND VA DOCTOR CHECK
:: ================================================================

echo.
echo [7/7] Dang cai Node.js dependencies...

if exist "%POSTER_DIR%\dist\storyboard-gen.js" (
    call pnpm --dir "%POSTER_DIR%" install --prod --frozen-lockfile
    if errorlevel 1 (
        echo [LOI] pnpm production install that bai.
        goto :FAIL
    )
    echo [OK] Da dung storyboard build san trong ban phat hanh.
) else (
    call pnpm --dir "%POSTER_DIR%" install --frozen-lockfile
    if errorlevel 1 (
        echo [LOI] pnpm install that bai.
        goto :FAIL
    )
    echo.
    echo [*] Dang build poster-generator tu source...
    call pnpm --dir "%POSTER_DIR%" build
    if errorlevel 1 (
        echo [LOI] Build poster-generator that bai.
        goto :FAIL
    )
)

echo.
echo [*] Dang chay Doctor Check...

:: Dam bao venv dang kich hoat
call "%VENV_DIR%\Scripts\activate.bat"
"%VENV_PYTHON%" "%ROOT%\audiobook.py" doctor

if errorlevel 1 (
    echo [LOI] Doctor Check phat hien thanh phan bat buoc chua san sang.
    goto :FAIL
)

echo [*] Dang xac minh ban cai hoan chinh...
"%VENV_PYTHON%" -c "import faster_whisper, PIL, torch, vieneu, yaml, yt_dlp; raise SystemExit(0 if torch.cuda.is_available() else 1)"
if errorlevel 1 goto :FAIL
if not exist "%POSTER_DIR%\dist\storyboard-gen.js" goto :FAIL
if not exist "%COMFYUI_MODELS%\DreamShaper_8_pruned.safetensors" goto :FAIL
if not exist "%COMFYUI_MODELS%\Realistic_Vision_V6.0_NV_B1_fp16.safetensors" goto :FAIL
if not exist "%IPADAPTER_MODELS%\ip-adapter_sd15.safetensors" goto :FAIL
if not exist "%CLIP_VISION_MODELS%\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors" goto :FAIL
powershell -NoProfile -Command "if((Get-FileHash -Algorithm SHA256 -LiteralPath '%COMFYUI_MODELS%\DreamShaper_8_pruned.safetensors').Hash -ne '%DREAMSHAPER_SHA256%'){exit 1}"
if errorlevel 1 (
    echo [LOI] DreamShaper checksum khong khop.
    goto :FAIL
)
powershell -NoProfile -Command "if((Get-FileHash -Algorithm SHA256 -LiteralPath '%COMFYUI_MODELS%\Realistic_Vision_V6.0_NV_B1_fp16.safetensors').Hash -ne '%REALISTIC_VISION_SHA256%'){exit 1}"
if errorlevel 1 (
    echo [LOI] Realistic Vision checksum khong khop.
    goto :FAIL
)
ollama show qwen2.5:1.5b >nul 2>&1
if errorlevel 1 goto :FAIL
ollama show qwen2.5:7b >nul 2>&1
if errorlevel 1 goto :FAIL
ollama show moondream >nul 2>&1
if errorlevel 1 goto :FAIL
powershell -NoProfile -Command "$m=[ordered]@{schema_version=2;installed_at=(Get-Date).ToString('o');comfyui_commit='%COMFYUI_COMMIT%';ipadapter_commit='%IPADAPTER_COMMIT%';python=(& '%VENV_PYTHON%' --version 2^>^&1);node=(& node --version);pnpm=(& pnpm --version);models=@('qwen2.5:1.5b','qwen2.5:7b','moondream','DreamShaper_8','Realistic_Vision_V6','IP-Adapter_SD15','CLIP_Vision_H')}; $m|ConvertTo-Json -Depth 4|Set-Content -LiteralPath '%ROOT%\.install-manifest.json' -Encoding utf8"
if errorlevel 1 goto :FAIL
echo [OK] Tat ca backend, model va dependency da san sang.


:: ================================================================
:: HOAN TAT
:: ================================================================

echo.
echo ================================================================
echo              HOAN TAT CAI DAT!
echo ================================================================
echo.
echo Cac buoc tiep theo:
echo   1. Web Interface dang duoc mo tu dong.
echo   2. Hoac chay CLI:     .\audiobook.bat build --help
echo.
echo De cap nhat sau nay:   .\install.bat
echo De xoa toan bo:        .\uninstall.bat
echo.

start "" /b "%ROOT%\audiobook.bat" web
exit /b 0


:: ================================================================
:: SUBROUTINES
:: ================================================================

:REFRESH_PATH
echo [*] Dang cap nhat PATH cua CMD hien tai...

for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$machine=[Environment]::GetEnvironmentVariable('Path','Machine'); $user=[Environment]::GetEnvironmentVariable('Path','User'); Write-Output ($machine + ';' + $user)"`) do (
    set "PATH=%%P"
)

set "PATH=%PATH%;%APPDATA%\npm"
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WindowsApps"
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
set "PATH=%PATH%;C:\Program Files\nodejs"
set "PATH=%PATH%;C:\Program Files\Git\cmd"

exit /b 0


:DETECT_PYTHON
set "PYTHON_CMD="

where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>&1

    if not errorlevel 1 (
        set "PYTHON_CMD=py -3.11"
        exit /b 0
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        exit /b 0
    )
)

exit /b 0


:ENSURE_OLLAMA
ollama list >nul 2>&1

if not errorlevel 1 (
    echo [OK] Ollama server dang hoat dong.
    exit /b 0
)

echo [*] Dang khoi dong Ollama server...

if exist "%OLLAMA_LOG%" del /q "%OLLAMA_LOG%" >nul 2>&1

start "" /b ollama serve >"%OLLAMA_LOG%" 2>&1

echo [*] Dang doi Ollama server san sang...

for /l %%I in (1,1,30) do (
    timeout /t 1 /nobreak >nul

    ollama list >nul 2>&1

    if not errorlevel 1 (
        echo [OK] Ollama server da san sang.
        exit /b 0
    )
)

echo [LOI] Ollama khong san sang sau 30 lan kiem tra.
exit /b 1


:FAIL
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"

echo.
echo ================================================================
echo [FAILED] CAI DAT THAT BAI
echo ================================================================
echo Ma loi: %EXIT_CODE%
echo.

pause
endlocal
exit /b %EXIT_CODE%
