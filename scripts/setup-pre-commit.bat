@echo off
echo [SETUP] Setting up pre-commit hooks for Common Chronicle
echo ============================================================

:: Check if we're in the right directory
if not exist "pyproject.toml" (
    echo [ERROR] Please run this script from the project root directory
    pause
    exit /b 1
)

echo [INSTALL] Installing pre-commit...
pip install pre-commit
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install pre-commit
    pause
    exit /b 1
)

echo [INFO] Installing git hook scripts...
pre-commit install
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install git hooks
    pause
    exit /b 1
)

echo [CHECK] Running pre-commit hooks on all files (this may take a while)...
pre-commit run --all-files
if %errorlevel% neq 0 (
    echo [WARNING] Some checks failed. Please fix the issues and try again.
    echo    You can run 'pre-commit run --all-files' to see what needs fixing.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Pre-commit hooks setup completed successfully!
echo.
echo [INFO] From now on, every time you commit, the following will run automatically:
echo    - Black (code formatting)
echo    - isort (import sorting)
echo    - autoflake (remove unused imports)
echo    - ruff (fast linting)
echo    - mypy (type checking)
echo    - General file checks
echo    - Frontend ESLint (for React/TypeScript files)
echo.
echo [TIPS] Pro tips:
echo    - To skip hooks temporarily: git commit --no-verify
echo    - To run hooks manually: pre-commit run --all-files
echo    - To update hook versions: pre-commit autoupdate
echo.
pause
