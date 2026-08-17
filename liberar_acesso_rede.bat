@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

netsh advfirewall firewall add rule name="Monitor NF-e Porta 8765" dir=in action=allow protocol=TCP localport=8765 profile=domain,private

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$s=New-Object Net.Sockets.UdpClient; try{$s.Connect('192.168.2.6',445); $s.Client.LocalEndPoint.Address.IPAddressToString}finally{$s.Dispose()}"`) do set "LAN_IP=%%I"

echo.
echo Acesso liberado.
echo Nos outros computadores, abra: http://%LAN_IP%:8765
pause
