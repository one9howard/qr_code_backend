$logs = docker logs --tail 500 insite_signs-web-1 2>&1
$logs | Out-File -Encoding UTF8 last_docker_logs.txt
