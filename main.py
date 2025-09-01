import asyncio
import logging
from fastapi import FastAPI, HTTPException, Request, Body
from pathlib import Path
import xml.etree.ElementTree as ET
from cryptography.fernet import Fernet, InvalidToken
import base64
import uvicorn
import subprocess
import sys
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
import json

from config_reader import ConfigReader
from bot_1 import Bot_1

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

def get_fernet_instance(encryption_key: str) -> Fernet:
    """Get Fernet instance with validated key."""
    key = validate_key(encryption_key)
    return Fernet(key)

def encrypt_data(data: Any, encryption_key: str) -> str:
    """Encrypt complete data package."""
    try:
        fernet = get_fernet_instance(encryption_key)
        
        json_data = json.dumps(data)
        
        encrypted_bytes = fernet.encrypt(json_data.encode())
        return encrypted_bytes.decode()
            
    except Exception as e:
        raise RuntimeError(f"Encryption failed: {str(e)}")

def decrypt_data(encrypted_data: str, encryption_key: str) -> Any:
    """Decrypt complete data package."""
    try:
        fernet = get_fernet_instance(encryption_key)
        
        # Decrypt the data
        decrypted_bytes = fernet.decrypt(encrypted_data.encode())
        
        # Parse JSON back to Python object
        return json.loads(decrypted_bytes.decode())
            
    except InvalidToken:
        raise ValueError("Invalid encryption key or corrupted data")
    except json.JSONDecodeError:
        raise ValueError("Decrypted data is not valid JSON")
    except Exception as e:
        raise RuntimeError(f"Decryption failed: {str(e)}")

async def get_encryption_key() -> str:
    """Get encryption key from configuration."""
    config_reader = ConfigReader()
    config_data = config_reader.get_config_dict()
    
    if 'encryption_key' not in config_data:
        raise ValueError("Missing 'encryption_key' in configuration")
    
    return config_data['encryption_key']

def check_encryption_key() -> bool:
    """Перевірка наявності та валідності encryption_key в конфігурації"""
    try:
        config_reader = ConfigReader()
        config_data = config_reader.get_config_dict()
        
        # Перевірка наявності ключа
        if 'encryption_key' not in config_data:
            logger.warning("encryption_key відсутній у конфігураційному файлі")
            return False
        
        # Перевірка що ключ не пустий
        encryption_key = config_data['encryption_key']
        if not encryption_key or encryption_key.strip() == '':
            logger.warning("encryption_key пустий у конфігураційному файлі")
            return False
        
        # Спроба створити Fernet instance для валідації ключа
        try:
            get_fernet_instance(encryption_key)
            logger.info("encryption_key валідний")
            return True
        except Exception as e:
            logger.warning(f"encryption_key невалідний: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Помилка при перевірці encryption_key: {str(e)}")
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for FastAPI app"""
    # Startup
    logger.info("Сервер запускається...")
    
    # Перевірка encryption_key перед запуском
    if not check_encryption_key():
        logger.error("Невалідний encryption_key. Відновлення старої конфігурації...")
        if restore_old_config():
            logger.info("Конфігурація відновлена. Перезапуск сервера...")
            await perform_restart()
        else:
            logger.error("Не вдалося відновити стару конфігурацію")
    
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

async def perform_restart():
    """Perform server restart asynchronously"""
    await asyncio.sleep(1)  # Даємо час для відправки відповіді
    restart_bot()

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
            logger.warning("Старий конфігураційний файл не знайдено для відновлення")
            return False
        
        if config_path.exists():
            config_path.unlink()
        
        old_config_path.rename(config_path)
        logger.info("Конфігураційний файл успішно відновлено з резервної копії")
        return True
    except Exception as e:
        logger.error(f"Failed to restore old config: {str(e)}")
        return False

def read_config_file():
    """Read and parse the current config file."""
    try:
        config_path = Path(__file__).parent / "bot.config"
        
        if not config_path.exists():
            return {"error": "Config file not found"}
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_content = f.read()
        
        # Спроба парсингу XML
        try:
            root = ET.fromstring(config_content)
            config_data = {}
            for child in root:
                config_data[child.tag] = child.text
            return {"content": config_content, "parsed": config_data}
        except ET.ParseError:
            # Якщо не XML, повертаємо як текст
            return {"content": config_content, "parsed": None}
            
    except Exception as e:
        return {"error": f"Failed to read config: {str(e)}"}

def get_config_info():
    """Get information about config file."""
    try:
        config_path = Path(__file__).parent / "bot.config"
        
        if not config_path.exists():
            return {"exists": False, "size": 0, "modified": None}
        
        stats = config_path.stat()
        return {
            "exists": True,
            "size": stats.st_size,
            "modified": stats.st_mtime,
            "path": str(config_path)
        }
    except Exception as e:
        return {"error": f"Failed to get config info: {str(e)}"}

@app.post("/status")
async def server_status_encrypted(request: Request):
    """Ендпоінт для перевірки статусу сервера (повністю шифрований)"""
    try:
        encryption_key = await get_encryption_key()
        
        # Отримуємо та дешифруємо запит
        encrypted_request = await request.body()
        decrypted_data = decrypt_data(encrypted_request.decode(), encryption_key)
        
        logger.info(f"Отримано запит статусу: {decrypted_data}")
        
        # Готуємо відповідь
        response_data = {
            "status": "OK",
            "server_time": asyncio.get_event_loop().time(),
            "endpoints": ["/status", "/full-restart", "/receive-encrypted", "/update-config", "/restore-config", "/get-config", "/get-config-info"]
        }
        
        # Шифруємо всю відповідь
        encrypted_response = encrypt_data(response_data, encryption_key)
        return encrypted_response
        
    except Exception as e:
        logger.error(f"Помилка в ендпоінті статусу: {str(e)}")
        error_data = {"error": str(e), "status_code": 500}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error

@app.post("/full-restart")
async def full_restart_encrypted(request: Request):
    """Ендпоінт для повного перезапуска сервера (повністю шифрований)"""
    try:
        encryption_key = await get_encryption_key()
        
        # Отримуємо та дешифруємо запит
        encrypted_request = await request.body()
        decrypted_data = decrypt_data(encrypted_request.decode(), encryption_key)
        
        logger.info(f"Отримано запит перезапуску: {decrypted_data}")
        
        # Можна додати додаткову перевірку автентифікації тут
        if decrypted_data.get("auth_token") != "secure-token":
            raise ValueError("Invalid authentication token")
        
        logger.info("Ініційовано повний перезапуск сервера")
        
        # Готуємо відповідь перед перезапуском
        response_data = {
            "status": "restarting",
            "message": "Server is restarting",
            "timestamp": asyncio.get_event_loop().time()
        }
        
        encrypted_response = encrypt_data(response_data, encryption_key)
        
        # Перезапускаємо сервер (асинхронно)
        asyncio.create_task(perform_restart())
        
        return encrypted_response
        
    except Exception as e:
        logger.error(f"Помилка при перезапуску сервера: {str(e)}")
        error_data = {"error": str(e), "status_code": 500}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error

@app.post("/receive-encrypted")
async def receive_encrypted_data(request: Request):
    """Endpoint to receive and decrypt encrypted data (fully encrypted)"""
    global decrypted_config_data
    
    try:
        encryption_key = await get_encryption_key()
        
        # Отримуємо та дешифруємо запит
        encrypted_request = await request.body()
        decrypted_data = decrypt_data(encrypted_request.decode(), encryption_key)
        
        if not isinstance(decrypted_data, dict):
            raise ValueError("Expected a dictionary with encrypted data")
        
        # Виводимо дешифровані дані в термінал
        print("\n" + "="*50)
        print("Decrypted Data Received:")
        for key, value in decrypted_data.items():
            print(f"{key}: {value}")
        print("="*50 + "\n")
        
        # Зберігаємо дешифровані дані та сигналізуємо про отримання
        decrypted_config_data = decrypted_data
        config_received_event.set()
        
        # Шифруємо всю відповідь
        response_data = {"status": "success", "message": "Data received successfully"}
        encrypted_response = encrypt_data(response_data, encryption_key)
        
        return encrypted_response
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        error_data = {"error": str(e), "status_code": 400}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        error_data = {"error": f"Failed to process data: {str(e)}", "status_code": 500}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error

@app.post("/update-config")
async def update_config_endpoint(request: Request):
    """Ендпоінт для перезапису даних файла конфіга (повністю шифрований)"""
    try:
        encryption_key = await get_encryption_key()
        
        # Отримуємо та дешифруємо запит
        encrypted_request = await request.body()
        decrypted_data = decrypt_data(encrypted_request.decode(), encryption_key)
        
        # Очікуємо, що дані містять поле 'config_data'
        if 'config_data' not in decrypted_data:
            raise ValueError("Missing 'config_data' in request")
        
        new_config_data = decrypted_data['config_data']
        
        if update_config(new_config_data):
            # Готуємо відповідь перед перезапуском
            response_data = {"status": "success", "message": "Config updated, restarting"}
            encrypted_response = encrypt_data(response_data, encryption_key)
            
            # Перезапускаємо асинхронно
            asyncio.create_task(perform_restart())
            
            return encrypted_response
        else:
            raise RuntimeError("Failed to update config")
            
    except Exception as e:
        logger.error(f"Error updating config: {str(e)}")
        error_data = {"error": str(e), "status_code": 500}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error

@app.post("/restore-config")
async def restore_config_endpoint(request: Request):
    """Ендпоінт для повернення старого файла конфіга (повністю шифрований)"""
    try:
        encryption_key = await get_encryption_key()
        
        # Отримуємо та дешифруємо запит
        encrypted_request = await request.body()
        decrypted_data = decrypt_data(encrypted_request.decode(), encryption_key)
        
        if restore_old_config():
            # Готуємо відповідь перед перезапуском
            response_data = {"status": "success", "message": "Config restored, restarting"}
            encrypted_response = encrypt_data(response_data, encryption_key)
            
            # Перезапускаємо асинхронно
            asyncio.create_task(perform_restart())
            
            return encrypted_response
        else:
            error_data = {"error": "No backup config found", "status_code": 404}
            encrypted_error = encrypt_data(error_data, encryption_key)
            return encrypted_error
            
    except Exception as e:
        logger.error(f"Error restoring config: {str(e)}")
        error_data = {"error": str(e), "status_code": 500}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error

@app.post("/get-config")
async def get_config_endpoint(request: Request):
    """Ендпоінт для отримання даних з конфігураційного файлу (повністю шифрований)"""
    try:
        encryption_key = await get_encryption_key()
        
        # Отримуємо та дешифруємо запит
        encrypted_request = await request.body()
        decrypted_data = decrypt_data(encrypted_request.decode(), encryption_key)
        
        # Отримуємо інформацію про конфіг файл
        config_info = get_config_info()
        
        # Отримуємо вміст конфіг файлу
        config_content = read_config_file()
        
        # Формуємо відповідь
        response_data = {
            "status": "success",
            "config_info": config_info,
            "config_content": config_content
        }
        
        # Шифруємо всю відповідь
        encrypted_response = encrypt_data(response_data, encryption_key)
        return encrypted_response
            
    except Exception as e:
        logger.error(f"Error getting config: {str(e)}")
        error_data = {"error": str(e), "status_code": 500}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error

@app.post("/get-config-info")
async def get_config_info_endpoint(request: Request):
    """Ендпоінт для отримання інформації про конфігураційний файл (повністю шифрований)"""
    try:
        encryption_key = await get_encryption_key()
        
        # Отримуємо та дешифруємо запит
        encrypted_request = await request.body()
        decrypted_data = decrypt_data(encrypted_request.decode(), encryption_key)
        
        # Отримуємо інформацію про конфіг файл
        config_info = get_config_info()
        
        # Формуємо відповідь
        response_data = {
            "status": "success",
            "config_info": config_info
        }
        
        # Шифруємо всю відповідь
        encrypted_response = encrypt_data(response_data, encryption_key)
        return encrypted_response
            
    except Exception as e:
        logger.error(f"Error getting config info: {str(e)}")
        error_data = {"error": str(e), "status_code": 500}
        encryption_key = await get_encryption_key()
        encrypted_error = encrypt_data(error_data, encryption_key)
        return encrypted_error

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
        # Додаткова перевірка encryption_key перед запуском сервера
        if not check_encryption_key():
            logger.error("Невалідний encryption_key. Відновлення старої конфігурації...")
            if restore_old_config():
                logger.info("Конфігурація відновлена. Перезапуск сервера...")
                await perform_restart()
                return
            else:
                logger.error("Не вдалося відновити стару конфігурацію. Завершення роботи.")
                return
        
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