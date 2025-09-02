
import asyncio
import requests
import time
import sys
import os

async def monitor_restart():
    """Моніторинг перезапуску сервера"""
    print("Монітор: запуск моніторингу перезапуску сервера")
    
    timeout = 120
    max_attempts = timeout // 5
    attempt = 0
    
    while attempt < max_attempts:
        try:
            response = requests.get("http://localhost:8000/health", timeout=10)
            if response.status_code == 200:
                print("Монітор: сервер успішно перезапущено")
                return True
        except Exception as e:
            pass
        
        attempt += 1
        time.sleep(5)
    
    print("Монітор: перевищено час очікування перезапуску")
    return False

if __name__ == "__main__":
    success = asyncio.run(monitor_restart())
    sys.exit(0 if success else 1)
            