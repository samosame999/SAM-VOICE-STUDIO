@echo off
echo ===== NVIDIA GPU & CUDA =====
nvidia-smi
echo.
echo ===== Python 3.11 =====
py -3.11 --version
echo.
if exist .venv (
    echo ===== PyTorch & CUDA Check in .venv =====
    call .venv\Scripts\activate
    python diagnose_gpu.py
)
echo.
pause
