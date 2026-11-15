@echo off
chcp 65001 >nul
echo ============================================
echo   IKGR 数据迁移 - 打包工具
echo ============================================
echo.

set "PROJECT_DIR=D:\IKGR-system-eands"
set "OUTPUT_DIR=%PROJECT_DIR%\deploy"
set "ZIP_FILE=%OUTPUT_DIR%\migration-package.zip"

echo [1/3] 检查必要文件...
if not exist "%PROJECT_DIR%\migration_data.sql" (
    echo ❌ 错误: migration_data.sql 不存在
    echo    请先运行: python export_migration.py
    pause
    exit /b 1
)
echo ✅ 找到 migration_data.sql

if not exist "%PROJECT_DIR%\deploy\import_migration.sh" (
    echo ❌ 错误: import_migration.sh 不存在
    pause
    exit /b 1
)
echo ✅ 找到 import_migration.sh

echo.
echo [2/3] 创建部署包...

REM 创建临时目录结构
set "TEMP_DIR=%TEMP%\ikgr-migration"
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"

REM 复制文件
copy "%PROJECT_DIR%\migration_data.sql" "%TEMP_DIR%\" >nul
copy "%PROJECT_DIR%\deploy\import_migration.sh" "%TEMP_DIR%\" >nul
copy "%PROJECT_DIR%\docs\数据迁移操作指南.md" "%TEMP_DIR%\" >nul 2>nul

REM 打包为 zip
cd /d "%TEMP%"
powershell -Command "Compress-Archive -Path * -DestinationPath '%ZIP_FILE%' -Force"

REM 清理临时目录
cd /d "%PROJECT_DIR%"
rmdir /s /q "%TEMP_DIR%"

echo ✅ 打包完成

echo.
echo [3/3] 验证输出...
if exist "%ZIP_FILE%" (
    for %%A in ("%ZIP_FILE%") do (
        set SIZE=%%~zA
        set /a SIZE_MB=!SIZE! / 1024 / 1024
    )
    echo 📦 部署包: %ZIP_FILE%
    for %%I in ("%ZIP_FILE%") do echo 📏 大小: %%~zI bytes
) else (
    echo ❌ 打包失败
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ✅ 准备完成！
echo ============================================
echo.
echo 📋 下一步操作:
echo.
echo   1. 上传部署包到服务器:
echo      scp %ZIP_FILE% root@114.55.116.162:/tmp/
echo.
echo   2. SSH 登录服务器并解压:
echo      ssh root@114.55.116.162
echo      cd /tmp
echo      unzip migration-package.zip
echo.
echo   3. 执行一键导入:
echo      chmod +x import_migration.sh
echo      bash import_migration.sh
echo.
echo   或者查看详细指南:
echo      cat 数据迁移操作指南.md
echo.
pause
