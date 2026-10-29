@echo off
rem Runs every integration test project (test_*) in this folder.
rem Each project is run from its own folder with config\env.yaml and config\test.yaml,
rem unless it has its own run_testset.bat, which is then called from that folder with
rem the python interpreter as its argument (e.g. testset_02, which checks --interactive).
rem Uses the repository's .venv if it exists, otherwise the python on PATH.

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "PYTHON=%ROOT%..\..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

set "RESULT=0"
for /d %%D in ("%ROOT%testset_*") do (
    echo.
    echo ===== %%~nxD =====
    pushd "%%D"
    if exist "run_testset.bat" (
        call run_testset.bat "%PYTHON%"
    ) else (
        "%PYTHON%" -m fixturerig --config config\env.yaml --config config\test.yaml
    )
    if errorlevel 1 (
        echo %%~nxD exited with code !errorlevel!
        set "RESULT=1"
    )
    popd
)

exit /b %RESULT%
