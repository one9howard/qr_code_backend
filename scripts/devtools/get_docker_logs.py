import subprocess
import asyncio

async def get_logs_async():
    # Run docker logs command
    process = await asyncio.create_subprocess_exec(
        'docker', 'logs', 'insite_signs-web-1',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    # Decode output
    try:
        logs = stdout.decode('utf-8') + stderr.decode('utf-8')
    except UnicodeDecodeError: 
        logs = stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')
        
    print(logs)

# Run the async function
asyncio.run(get_logs_async())
