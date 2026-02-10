@echo off

REM Check Python installation
echo [1/8] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11 or higher.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

REM Create virtual environment
echo [2/8] Creating virtual environment...
if exist qc_env (
    echo Virtual environment already exists. Skipping creation.
) else (
    python -m venv qc_env
    echo Virtual environment created successfully.
)
echo.

REM Activate virtual environment
echo [3/8] Activating virtual environment...
call qc_env\Scripts\activate.bat
echo Virtual environment activated.
echo.

REM Upgrade pip
echo [4/8] Upgrading pip...
python -m pip install --upgrade pip
echo.

REM Install dependencies
echo [5/8] Installing dependencies...
echo Installing Qiskit...
pip install qiskit==1.0.1
echo Installing NumPy...
pip install numpy==1.26.3
echo Installing SciPy...
pip install scipy==1.12.0
echo Installing Matplotlib...
pip install matplotlib==3.8.2
echo Installing PyYAML...
pip install pyyaml==6.0.1
echo All dependencies installed.
echo.

REM Freeze requirements
echo [6/8] Freezing requirements...
pip freeze > requirements.txt
echo Requirements saved to requirements.txt
echo.

REM Create project structure
echo [7/8] Creating project structure...

mkdir src 2>nul
mkdir src\agents 2>nul
mkdir src\coordination 2>nul
mkdir src\evaluation 2>nul
mkdir experiments 2>nul
mkdir experiments\configs 2>nul
mkdir experiments\results 2>nul
mkdir experiments\logs 2>nul
mkdir docs 2>nul
mkdir tests 2>nul
mkdir notebooks 2>nul

REM Create __init__.py files
type nul > src\__init__.py
type nul > src\agents\__init__.py
type nul > src\coordination\__init__.py
type nul > src\evaluation\__init__.py

echo Project structure created.
echo.

REM Verification tests
echo [8/8] Running verification tests...
echo.

echo Test 1: Qiskit import
python -c "import qiskit; print('Qiskit version:', qiskit.__version__)"
if errorlevel 1 (
    echo FAILED: Qiskit import failed
    pause
    exit /b 1
)
echo.

echo Test 2: NumPy import
python -c "import numpy; print('NumPy version:', numpy.__version__)"
if errorlevel 1 (
    echo FAILED: NumPy import failed
    pause
    exit /b 1
)
echo.

echo Test 3: All imports
python -c "import qiskit, numpy, scipy, matplotlib, yaml; print('All imports successful!')"
if errorlevel 1 (
    echo FAILED: Some imports failed
    pause
    exit /b 1
)
echo.

REM Display project structure
echo Project structure:
tree /F /A
echo.

echo Setup Complete!
pause