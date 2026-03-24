#!/usr/bin/env pwsh
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptDir

Set-Location $ProjectRoot
jarvis-service
