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
  models  = @{
    'grok-4.5'        = @{ name = 'BU grok-4.5' }
    'gpt-5.5'         = @{ name = 'BU gpt-5.5' }
    'claude-sonnet-5' = @{ name = 'BU claude-sonnet-5' }
    'kimi-k3'         = @{ name = 'BU kimi-k3' }
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
