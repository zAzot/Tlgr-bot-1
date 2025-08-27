from telethon import TelegramClient
from telethon.tl.types import PeerChannel

async def get_last_channel_message(config_data=None):
    """
    Отримання останнього повідомлення з каналу
    Повертає словник з інформацією:
    {
        "success": bool,
        "message": str,
        "error": str (якщо success=False)
    }
    """
    try:
        # Перевіряємо обов'язкові параметри
        if not config_data:
            return {
                "success": False,
                "error": "Відсутні дані конфігурації"
            }
        
        required_params = ['ApiId', 'ApiHash', 'PhoneNumber', 'TargetChats']
        for param in required_params:
            if not config_data.get(param):
                return {
                    "success": False,
                    "error": f"В конфігурації відсутній параметр {param}"
                }
        
        # Отримуємо ID каналу (перший зі списку)
        target_chats = config_data['TargetChats']
        
        # Переконуємося, що target_chats є рядком перед викликом split()
        if not isinstance(target_chats, str):
            target_chats = str(target_chats)
        
        # Розділяємо по комах і беремо перший елемент
        channel_ids = [id_str.strip() for id_str in target_chats.split(',')]
        channel_id = channel_ids[0] if channel_ids else None
        
        if not channel_id:
            return {
                "success": False,
                "error": "Не вказано ID каналу в конфігурації"
            }
        
        # Підключаємося до Telegram
        async with TelegramClient(
            'session_name', 
            int(config_data['ApiId']), 
            config_data['ApiHash']
        ) as client:
            await client.start(phone=config_data['PhoneNumber'])
            
            # Отримуємо останнє повідомлення
            messages = await client.get_messages(
                entity=PeerChannel(int(channel_id)),
                limit=1
            )
            
            if not messages:
                return {
                    "success": True,
                    "message": "[Канал порожній]"
                }
            
            last_message = messages[0]
            message_text = last_message.text or "[Медіа-повідомлення без тексту]"
            
            return {
                "success": True,
                "message": message_text,
                "date": last_message.date.isoformat()
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Помилка при отриманні повідомлення: {str(e)}"
        }