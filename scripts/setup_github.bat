@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  UniTrade GitHub Issues Creator - CMD Version
::  Usage: setup_github.bat Rezkydesyafa/unitrade
:: ============================================================

set REPO=%1

if "%REPO%"=="" (
    echo.
    echo ERROR: Masukkan nama repo!
    echo Usage: setup_github.bat Rezkydesyafa/unitrade
    echo.
    pause
    exit /b 1
)

echo.
echo ======================================================
echo   UniTrade GitHub Setup
echo   Repo: %REPO%
echo ======================================================
echo.

:: ── CEK gh CLI ────────────────────────────────────────────
gh --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: GitHub CLI tidak ditemukan!
    echo Download di: https://cli.github.com
    pause
    exit /b 1
)
echo [OK] GitHub CLI ditemukan!
echo.

:: ── CEK LOGIN ─────────────────────────────────────────────
echo Mengecek status login...
gh auth status >nul 2>&1
if %errorlevel% neq 0 (
    echo Belum login. Menjalankan gh auth login...
    gh auth login
)
echo [OK] Sudah login!
echo.

:: ══════════════════════════════════════════════════════════
:: STEP 1 - BUAT LABELS
:: ══════════════════════════════════════════════════════════
echo [1/3] Membuat Labels...
echo.

gh label create "priority:critical" --color "EF4444" --description "Blocker, harus selesai duluan" --repo %REPO% --force 2>nul & echo    [OK] priority:critical
gh label create "priority:high"     --color "F59E0B" --description "Penting" --repo %REPO% --force 2>nul & echo    [OK] priority:high
gh label create "priority:medium"   --color "3B82F6" --description "Perlu tapi tidak blocker" --repo %REPO% --force 2>nul & echo    [OK] priority:medium
gh label create "priority:low"      --color "94A3B8" --description "Nice to have" --repo %REPO% --force 2>nul & echo    [OK] priority:low
gh label create "setup"       --color "6366F1" --repo %REPO% --force 2>nul & echo    [OK] setup
gh label create "auth"        --color "8B5CF6" --repo %REPO% --force 2>nul & echo    [OK] auth
gh label create "seller"      --color "EC4899" --repo %REPO% --force 2>nul & echo    [OK] seller
gh label create "product"     --color "F43F5E" --repo %REPO% --force 2>nul & echo    [OK] product
gh label create "payment"     --color "10B981" --repo %REPO% --force 2>nul & echo    [OK] payment
gh label create "delivery"    --color "06B6D4" --repo %REPO% --force 2>nul & echo    [OK] delivery
gh label create "chat"        --color "F59E0B" --repo %REPO% --force 2>nul & echo    [OK] chat
gh label create "notification"--color "0EA5E9" --repo %REPO% --force 2>nul & echo    [OK] notification
gh label create "review"      --color "D97706" --repo %REPO% --force 2>nul & echo    [OK] review
gh label create "admin"       --color "1E293B" --repo %REPO% --force 2>nul & echo    [OK] admin
gh label create "frontend"    --color "0284C7" --repo %REPO% --force 2>nul & echo    [OK] frontend
gh label create "backend"     --color "475569" --repo %REPO% --force 2>nul & echo    [OK] backend
gh label create "ui"          --color "7DD3FC" --repo %REPO% --force 2>nul & echo    [OK] ui
gh label create "ocr"         --color "F97316" --repo %REPO% --force 2>nul & echo    [OK] ocr
gh label create "location"    --color "16A34A" --repo %REPO% --force 2>nul & echo    [OK] location
gh label create "qa"          --color "7C3AED" --repo %REPO% --force 2>nul & echo    [OK] qa
gh label create "security"    --color "DC2626" --repo %REPO% --force 2>nul & echo    [OK] security
gh label create "performance" --color "CA8A04" --repo %REPO% --force 2>nul & echo    [OK] performance
gh label create "deploy"      --color "059669" --repo %REPO% --force 2>nul & echo    [OK] deploy
gh label create "devops"      --color "334155" --repo %REPO% --force 2>nul & echo    [OK] devops
gh label create "uat"         --color "7E22CE" --repo %REPO% --force 2>nul & echo    [OK] uat

echo.
echo [OK] Semua labels berhasil dibuat!
echo.

:: ══════════════════════════════════════════════════════════
:: STEP 2 - BUAT MILESTONES
:: ══════════════════════════════════════════════════════════
echo [2/3] Membuat Milestones...
echo.

gh api repos/%REPO%/milestones -f title="Phase 1 - Setup & Foundation"     -f due_on="2026-04-28T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 1
gh api repos/%REPO%/milestones -f title="Phase 2 - Auth & Profil"          -f due_on="2026-05-02T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 2
gh api repos/%REPO%/milestones -f title="Phase 3 - Verifikasi Seller"      -f due_on="2026-05-05T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 3
gh api repos/%REPO%/milestones -f title="Phase 4 - Produk & Katalog"       -f due_on="2026-05-08T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 4
gh api repos/%REPO%/milestones -f title="Phase 5 - Transaksi & Komunikasi" -f due_on="2026-05-12T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 5
gh api repos/%REPO%/milestones -f title="Phase 6 - Notifikasi"             -f due_on="2026-05-13T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 6
gh api repos/%REPO%/milestones -f title="Phase 7 - Dashboard Seller"       -f due_on="2026-05-16T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 7
gh api repos/%REPO%/milestones -f title="Phase 8 - Dashboard Admin"        -f due_on="2026-05-18T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 8
gh api repos/%REPO%/milestones -f title="Phase 9 - Lokasi & Bantuan"       -f due_on="2026-05-20T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 9
gh api repos/%REPO%/milestones -f title="Phase 10 - QA & Deploy"           -f due_on="2026-05-22T00:00:00Z" >nul 2>&1 & echo    [OK] Phase 10

echo.
echo [OK] Semua milestones berhasil dibuat!
echo.

:: ══════════════════════════════════════════════════════════
:: STEP 3 - BUAT ISSUES via Python
:: ══════════════════════════════════════════════════════════
echo [3/3] Membuat 45 Issues via Python...
echo.

python create_issues.py %REPO%

echo.
echo ======================================================
echo   SELESAI!
echo   Buka: https://github.com/%REPO%/issues
echo ======================================================
pause
