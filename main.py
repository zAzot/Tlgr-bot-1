import asyncio
import logging
from fastapi import FastAPI, HTTPException, Request
from pathlib import Path
import xml.etree.ElementTree as ET
from cryptography.fernet import Fernet, InvalidToken
import base64
import uvicorn
import subprocess
import sys
from typing import Dict, Any
from contextlib import asynccontextmanager

from config_reader import ConfigReader
from bot_1 import Bot_1

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальна змінна для зберігання дешифрованих даних
decrypted_config_data = None
config_received_event = asyncio.Event()

def validate_key(key: str) -> bytes:
    """Validate and prepare the encryption key."""
    try:
        if len(key) < 32:
            key = key.ljust(32)[:32]
        elif len(key) > 32:
            key = key[:32]
        
        return base64.urlsafe_b64encode(key.encode())
    except Exception as e:
        raise ValueError(f"Invalid key format: {str(e)}")

def decrypt_single_value(encrypted_value: str, encryption_key: str) -> str:
    """Decrypt a single encrypted value."""
    try:
        key = validate_key(encryption_key)
        fernet = Fernet(key)
        
        # Переконуємося, що значення є рядком перед декодуванням
        if isinstance(encrypted_value, bytes):
            encrypted_bytes = encrypted_value
        else:
            encrypted_bytes = encrypted_value.encode()
        
        decrypted_value = fernet.decrypt(encrypted_bytes)
        return decrypted_value.decode()
            
    except InvalidToken:
        raise ValueError("Invalid encryption key or corrupted data")
    except Exception as e:
        raise RuntimeError(f"Decryption failed: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for FastAPI app"""
    # Startup
    logger.info("Сервер запускається...")
    yield
    # Shutdown
    logger.info("Сервер зупиняється...")

app = FastAPI(lifespan=lifespan)

def restart_bot():
    """Перезапуск бота"""
    try:
        python_executable = sys.executable
        script_path = sys.argv[0]
        subprocess.Popen([python_executable, script_path])
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to restart bot: {str(e)}")
        raise

def update_config(new_config_data: str) -> bool:
    """Оновлення конфігураційного файлу"""
    try:
        config_path = Path(__file__).parent / "bot.config"
        old_config_path = Path(__file__).parent / "bot_old.config"
        
        if config_path.exists():
            if old_config_path.exists():
                old_config_path.unlink()
            config_path.rename(old_config_path)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_config_data)
        
        return True
    except Exception as e:
        logger.error(f"Failed to update config: {str(e)}")
        return False

def restore_old_config() -> bool:
    """Відновлення старого конфігураційного файлу"""
    try:
        config_path = Path(__file__).parent / "bot.config"
        old_config_path = Path(__file__).parent / "bot_old.config"
        
        if not old_config_path.exists():
            return False
        
        if config_path.exists():
            config_path.unlink()
        
        old_config_path.rename(config_path)
        
        return True
    except Exception as e:
        logger.error(f"Failed to restore old config: {str(e)}")
        return False

@app.post("/receive-encrypted")
async def receive_encrypted_data(request: Request):
    """Endpoint to receive and decrypt encrypted data."""
    global decrypted_config_data
    
    try:
        # Отримуємо конфігурацію для encryption_key
        config_reader = ConfigReader()
        config_data = config_reader.get_config_dict()
        
        # Перевіряємо наявність encryption_key
        if 'encryption_key' not in config_data:
            raise ValueError("Missing 'encryption_key' in configuration")
        
        # Отримуємо зашифровані дані з запиту
        encrypted_package = await request.json()
        
        if not isinstance(encrypted_package, dict):
            raise ValueError("Expected a JSON object with encrypted data")
        
        # Дешифруємо кожне значення в пакеті
        decrypted_data = {}
        for key, encrypted_value in encrypted_package.items():
            try:
                decrypted_value = decrypt_single_value(encrypted_value, config_data['encryption_key'])
                decrypted_data[key] = decrypted_value
            except Exception as e:
                logger.error(f"Failed to decrypt {key}: {str(e)}")
                raise ValueError(f"Decryption failed for {key}")
        
        # Виводимо дешифровані дані в термінал
        print("\n" + "="*50)
        print("Decrypted Data Received:")
        for key, value in decrypted_data.items():
            print(f"{key}: {value}")
        print("="*50 + "\n")
        
        # Зберігаємо дешифровані дані та сигналізуємо про отримання
        decrypted_config_data = decrypted_data
        config_received_event.set()
        
        # Повертаємо лише статус код
        return {"status_code": 200}
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to decrypt data: {str(e)}")

@app.post("/update-config")
async def update_config_endpoint(request: Request):
    """Ендпоінт для перезапису даних файла конфіга"""
    try:
        new_config_data = await request.body()
        new_config_data = new_config_data.decode('utf-8')
        
        if update_config(new_config_data):
            restart_bot()
            return {"status_code": 200}
        else:
            return {"status_code": 500}
            
    except Exception as e:
        logger.error(f"Error updating config: {str(e)}")
        return {"status_code": 500}

@app.post("/restore-config")
async def restore_config_endpoint():
    """Ендпоінт для повернення старого файла конфіга"""
    try:
        if restore_old_config():
            restart_bot()
            return {"status_code": 200}
        else:
            return {"status_code": 404}
            
    except Exception as e:
        logger.error(f"Error restoring config: {str(e)}")
        return {"status_code": 500}

async def run_bot_with_config(config_data: dict):
    """Запуск бота з конфігураційними даними"""
    try:
        if not config_data.get('Token'):
            raise ValueError("Token not found in configuration")
        
        # Створюємо та запускаємо бота
        bot = Bot_1(config_data=config_data)
        await bot.run()
        
    except Exception as e:
        logger.error(f"Помилка при запуску бота: {str(e)}")
        raise

async def start_server():
    """Запуск сервера FastAPI"""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    """Головна функція, яка запускає сервер та очікує дешифровані дані"""
    global decrypted_config_data
    
    try:
        # Запускаємо сервер у фоновому режимі
        server_task = asyncio.create_task(start_server())
        
        logger.info("Сервер запущений на порту 8000. Очікування дешифрованих даних...")
        
        # Очікуємо отримання дешифрованих даних
        await config_received_event.wait()
        
        if decrypted_config_data is None:
            raise ValueError("Не отримано дешифровані дані")
        
        logger.info("Дешифровані дані отримані. Завантаження конфігурації з файлу...")
        
        # Отримуємо решту конфігурації з файлу
        config_reader = ConfigReader()
        file_config_data = config_reader.get_config_dict()
        
        # Об'єднуємо дешифровані дані з файловими даними
        final_config_data = {**file_config_data, **decrypted_config_data}
        
        logger.info("Конфігурація завантажена. Запуск бота...")
        
        # Зупиняємо сервер перед запуском бота
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            logger.info("Сервер зупинено")
        
        # Запускаємо бота з об'єднаною конфігурацією
        await run_bot_with_config(final_config_data)
        
    except asyncio.CancelledError:
        logger.info("Робота перервана")
    except Exception as e:
        logger.error(f"Помилка при запуску програми: {str(e)}")
        # Гарантуємо зупинку сервера при помилці
        if 'server_task' in locals():
            server_task.cancel()
    finally:
        logger.info("Програма завершена")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот зупинений користувачем")
    except Exception as e:
        logger.error(f"Невідома помилка: {str(e)}")