from telethon import TelegramClient
from telethon.tl.types import PeerChannel
import asyncio
import logging

logger = logging.getLogger(__name__)

# Глобальний клієнт для уникнення конфліктів сесій
_client = None
_client_lock = asyncio.Lock()

async def get_telegram_client(config_data):
    """Отримати або створити клієнт Telegram з блокуванням"""
    global _client
    
    async with _client_lock:
        if _client is None:
            try:
                _client = TelegramClient(
                    'session_name', 
                    int(config_data['ApiId']), 
                    config_data['ApiHash']
                )
                await _client.start(phone=config_data['PhoneNumber'])
                logger.info("Telegram клієнт успішно ініціалізований")
            except Exception as e:
                logger.error(f"Помилка ініціалізації Telegram клієнта: {str(e)}")
                raise
        return _client

async def close_telegram_client():
    """Закрити клієнт Telegram"""
    global _client
    
    async with _client_lock:
        if _client:
            await _client.disconnect()
            _client = None
            logger.info("Telegram клієнт закритий")

async def get_last_channel_message(config_data=None, channel_id=None):
    """
    Отримання останнього повідомлення з конкретного каналу
    Повертає словник з інформацією:
    {
        "success": bool,
        "message": str,
        "channel_id": str,
        "error": str (якщо success=False)
    }
    """
    client = None
    try:
        # Перевіряємо обов'язкові параметри
        if not config_data:
            return {
                "success": False,
                "error": "Відсутні дані конфігурації",
                "channel_id": channel_id
            }
        
        if not channel_id:
            return {
                "success": False,
                "error": "Відсутній ID каналу",
                "channel_id": channel_id
            }
        
        required_params = ['ApiId', 'ApiHash', 'PhoneNumber']
        for param in required_params:
            if not config_data.get(param):
                return {
                    "success": False,
                    "error": f"В конфігурації відсутній параметр {param}",
                    "channel_id": channel_id
                }
        
        # Отримуємо клієнт з блокуванням
        client = await get_telegram_client(config_data)
        
        # Отримуємо останнє повідомлення
        messages = await client.get_messages(
            entity=PeerChannel(int(channel_id)),
            limit=1
        )
        
        if not messages:
            return {
                "success": True,
                "message": "[Канал порожній]",
                "channel_id": channel_id
            }
        
        last_message = messages[0]
        message_text = last_message.text or "[Медіа-повідомлення без тексту]"
        
        return {
            "success": True,
            "message": message_text,
            "channel_id": channel_id,
            "date": last_message.date.isoformat() if last_message.date else None
        }
            
    except Exception as e:
        logger.error(f"Помилка при отриманні повідомлення з каналу {channel_id}: {str(e)}")
        return {
            "success": False,
            "error": f"Помилка при отриманні повідомлення: {str(e)}",
            "channel_id": channel_id
        }

async def get_messages_from_all_channels(config_data=None):
    """
    Отримання останніх повідомлень з усіх каналів у списку
    Повертає список результатів для кожного каналу
    """
    try:
        if not config_data:
            return {
                "success": False,
                "error": "Відсутні дані конфігурації"
            }
        
        if 'TargetChats' not in config_data or not config_data['TargetChats']:
            return {
                "success": False,
                "error": "Відсутній список каналів у конфігурації"
            }
        
        # Отримуємо список ID каналів
        target_chats = config_data['TargetChats']
        
        # Переконуємося, що target_chats є рядком перед викликом split()
        if not isinstance(target_chats, str):
            target_chats = str(target_chats)
        
        # Розділяємо по комах, фільтруємо пусті значення
        channel_ids = [id_str.strip() for id_str in target_chats.split(',') if id_str.strip()]
        
        if not channel_ids:
            return {
                "success": False,
                "error": "Список каналів порожній"
            }
        
        # Отримуємо повідомлення з усіх каналів послідовно для уникнення блокування
        results = []
        for channel_id in channel_ids:
            try:
                result = await get_last_channel_message(config_data, channel_id)
                results.append(result)
                # Невелика затримка між запитами до різних каналів
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Помилка при обробці каналу {channel_id}: {str(e)}")
                results.append({
                    "success": False,
                    "error": f"Помилка обробки: {str(e)}",
                    "channel_id": channel_id
                })
        
        return {
            "success": True,
            "results": results,
            "total_channels": len(channel_ids),
            "successful_channels": sum(1 for r in results if r.get('success', False))
        }
            
    except Exception as e:
        logger.error(f"Помилка при отриманні повідомлень з каналів: {str(e)}")
        return {
            "success": False,
            "error": f"Помилка при отриманні повідомлень з каналів: {str(e)}"
        }