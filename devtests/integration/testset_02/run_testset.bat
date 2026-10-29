@echo off
rem Checks the --interactive option. Called by ..\run_integration_tests.bat with
rem the python interpreter as %1, from this folder.
rem
rem 1. Without --interactive the exception in test 2 is reported as ERROR, test 3
rem    still runs and the program exits with 0.
rem 2. With --interactive the exception ends the program: it exits non-zero with
rem    an InteractiveProbeError traceback, test 3 never runs, and the dut_shutdown
rem    step still runs.

setlocal

set "PYTHON=%~1"
if "%PYTHON%"=="" set "PYTHON=python"
set "OUT=%TEMP%\fixturerig_testset_02_%RANDOM%.txt"
set "FAILED=0"

echo --- run without --interactive
"%PYTHON%" -m fixturerig --config config\env.yaml --config config\test.yaml > "%OUT%" 2>&1
set "CODE=%errorlevel%"
type "%OUT%"
if "%CODE%"=="0" (echo   ok:   exit code is 0) else (echo   FAIL: exit code is 0 & set "FAILED=1")
call :expect "MARKER: test 3 ran" "test 3 ran"
call :expect "MARKER: dut_shutdown ran" "dut_shutdown ran"

echo --- run with --interactive
"%PYTHON%" -m fixturerig --config config\env.yaml --config config\test.yaml --interactive > "%OUT%" 2>&1
set "CODE=%errorlevel%"
type "%OUT%"
if not "%CODE%"=="0" (echo   ok:   exit code is not 0) else (echo   FAIL: exit code is not 0 & set "FAILED=1")
call :expect "tests.interactive.InteractiveProbeError: raised on purpose" "traceback ends with InteractiveProbeError"
call :expect "MARKER: test 1 ran" "test 1 ran"
call :reject "MARKER: test 3 ran" "test 3 did not run"
call :expect "MARKER: dut_shutdown ran" "dut_shutdown ran"

del "%OUT%"
exit /b %FAILED%

:expect
findstr /c:%1 "%OUT%" > nul
if errorlevel 1 (echo   FAIL: %~2 & set "FAILED=1") else (echo   ok:   %~2)
exit /b 0

:reject
findstr /c:%1 "%OUT%" > nul
if errorlevel 1 (echo   ok:   %~2) else (echo   FAIL: %~2 & set "FAILED=1")
exit /b 0
