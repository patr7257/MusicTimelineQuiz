# Interactive admin tool: lists every saved Hitster game in Upstash Redis
# (dry run), then deletes them only after you type "yes" to confirm. It never
# takes the Upstash REST URL or token as arguments: it prompts for both, so
# they never land in your shell history or get written to disk.
#
# Thin wrapper: all the logic lives in wipe-hitster-games.mjs (run with node)
# so the same script works in bash too.

$ErrorActionPreference = 'Stop'

Set-Location (Join-Path $PSScriptRoot '..')

node (Join-Path $PSScriptRoot 'wipe-hitster-games.mjs')
exit $LASTEXITCODE
