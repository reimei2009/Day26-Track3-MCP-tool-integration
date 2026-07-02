$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerPath = Join-Path $RepoRoot "implementation\mcp_server.py"

npx -y @modelcontextprotocol/inspector python $ServerPath
