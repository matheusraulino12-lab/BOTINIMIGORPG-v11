@echo off
title BOT RPG - Iniciando...

echo ============================================
echo 🔵 Iniciando o Bot...
echo ============================================
echo.

REM ----- 1. Verificar ambiente virtual -----
if exist venv (
    echo 🟦 Ativando ambiente virtual...
    call venv\Scripts\activate
) else (
    echo ⚠️ Nenhum ambiente virtual encontrado.
    echo O bot vai rodar usando o Python global.
    echo.
)

REM ----- 2. Rodar o bot -----
echo 🟩 Executando main.py...
echo.

python main.py

echo.
echo ============================================
echo 🔴 Bot finalizou ou ocorreu um erro.
echo Pressione qualquer tecla para fechar.
echo ============================================
pause >nul
