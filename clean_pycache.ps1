Get-ChildItem 'D:\Unitrade\Unitrade-Oddo\unitrade_admin' -Recurse -Filter '__pycache__' -Directory -ErrorAction SilentlyContinue |
    ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "removed: $($_.FullName)"
    }
Write-Host 'done.'
