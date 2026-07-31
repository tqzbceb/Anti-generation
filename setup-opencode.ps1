$ErrorActionPreference = 'Stop'
$dir  = Join-Path $env:USERPROFILE '.config\opencode'
$file = Join-Path $dir 'opencode.json'
New-Item -ItemType Directory -Force -Path $dir | Out-Null

function Save-Json($obj, $path) {
  $json = $obj | ConvertTo-Json -Depth 20
  [System.IO.File]::WriteAllText($path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

$bu = @{
  npm     = '@ai-sdk/openai-compatible'
  name    = 'BrowserUse'
  options = @{ baseURL = 'http://127.0.0.1:8787/v1'; apiKey = 'sk-anything' }
  models  = [ordered]@{
    'kimi-k3'          = @{ name = 'BU Kimi (kimi-k3)' }
    'glm-5.2'          = @{ name = 'BU GLM (glm-5.2)' }
    'grok-4.5'         = @{ name = 'BU Grok (grok-4.5)' }
    'minimax-m3'       = @{ name = 'BU MiniMax (minimax-m3)' }
    'claude-opus-4.7'  = @{ name = 'BU Claude Opus 4.7' }
    'claude-opus-4.8'  = @{ name = 'BU Claude Opus 4.8' }
    'claude-opus-5'    = @{ name = 'BU Claude Opus 5' }
    'claude-fable-5'   = @{ name = 'BU Claude Fable 5' }
    'claude-sonnet-5'  = @{ name = 'BU Claude Sonnet 5' }
    'gpt-5.5'          = @{ name = 'BU GPT 5.5' }
    'gpt-5.6'          = @{ name = 'BU GPT 5.6' }
    'gemini-3.6-flash' = @{ name = 'BU Gemini 3.6 Flash' }
    'gemini-3.5-flash' = @{ name = 'BU Gemini 3.5 Flash' }
    'gemini-3.1-pro'   = @{ name = 'BU Gemini 3.1 Pro' }
    'gemini-3-flash'   = @{ name = 'BU Gemini 3 Flash' }
  }
}

if (Test-Path $file) {
  Copy-Item $file "$file.bak" -Force
  try { $cfg = Get-Content $file -Raw | ConvertFrom-Json } catch {
    Write-Host "[WARN] Existing opencode.json is not plain JSON (maybe jsonc)."
    Write-Host "       Backup saved as opencode.json.bak - add the provider manually."
    exit 1
  }
  if (-not $cfg.provider) { $cfg | Add-Member -NotePropertyName provider -NotePropertyValue ([pscustomobject]@{}) }
  if ($cfg.provider.PSObject.Properties['browseruse']) { $cfg.provider.browseruse = $bu }
  else { $cfg.provider | Add-Member -NotePropertyName browseruse -NotePropertyValue $bu }
  Save-Json $cfg $file
  Write-Host "[OK] Merged into existing opencode.json (old file backed up as opencode.json.bak)"
} else {
  Save-Json ([ordered]@{ '$schema' = 'https://opencode.ai/config.json'; provider = @{ browseruse = $bu } }) $file
  Write-Host "[OK] Created $file"
}

Write-Host ""
Write-Host "DONE. Next: restart opencode, type  /models  and pick 'BU grok-4.5'."
