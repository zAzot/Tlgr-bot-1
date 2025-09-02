from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import asyncio
import logging
import json
import os
import re
from pathlib import Path

from telegram_module import get_messages_from_all_channels, get_last_channel_message

logger = logging.getLogger(__name__)

USERS_DB_FILE = "users_db.json"

class Bot_1:
    def __init__(self, config_data):
        self.config_data = config_data
        self.token = config_data.get('Token')
        self.message_patterns = config_data.get('MessagePatterns', {})
        self.admin_chat_id = config_data.get('AdminChatId')
        self.user_notifications = {}
        self.application = None
        self.previous_messages = {}
        self.channel_names = {}
    
    def load_users_db(self):
        if os.path.exists(USERS_DB_FILE):
            with open(USERS_DB_FILE, 'r') as f:
                return json.load(f)
        return {"users": []}
    
    def save_users_db(self, users_db):
        with open(USERS_DB_FILE, 'w') as f:
            json.dump(users_db, f)
    
    def add_user_to_db(self, user_id):
        users_db = self.load_users_db()
        if user_id not in users_db["users"]:
            users_db["users"].append(user_id)
            self.save_users_db(users_db)
    
    async def send_notification_to_users(self, app, message):
        """Надсилає повідомлення всім користувачам, які увімкнули сповіщення."""
        users_db = self.load_users_db()
        success_count = 0
        fail_count = 0
        
        for user_id in users_db["users"]:
            if self.user_notifications.get(user_id, True):
                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=message
                    )
                    success_count += 1
                    logger.info(f"Повідомлення відправлено до {user_id}")
                except Exception as e:
                    fail_count += 1
                    logger.warning(f"Не вдалося відправити повідомлення до {user_id}: {str(e)}")
                    if "Chat not found" in str(e) or "bot was blocked" in str(e).lower():
                        if user_id in users_db["users"]:
                            users_db["users"].remove(user_id)
                            self.save_users_db(users_db)
        
        logger.info(f"Відправлено повідомлень: {success_count}, невдало: {fail_count}")
        return success_count, fail_count
    
    async def turn_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.user_notifications[user_id] = True
        self.add_user_to_db(user_id)
        await update.message.reply_text("Сповіщення увімкнено!")
    
    async def turn_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.user_notifications[user_id] = False
        self.add_user_to_db(user_id)
        await update.message.reply_text("Сповіщення вимкнено!")
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Endpoint to check if server is running"""
        await update.message.reply_text("Бот був перезапущений. Система працює у штатному режимі!")
    
    async def channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показати список відстежуваних каналів"""
        try:
            target_chats = self.config_data.get('TargetChats', '')
            if not target_chats:
                await update.message.reply_text("Список каналів порожній")
                return
            
            channel_ids = [id_str.strip() for id_str in target_chats.split(',') if id_str.strip()]
            response = "Відстежувані канали:\n\n"
            
            for i, channel_id in enumerate(channel_ids, 1):
                response += f"{i}. Канал ID: {channel_id}\n"
            
            await update.message.reply_text(response)
            
        except Exception as e:
            await update.message.reply_text(f"Помилка при отриманні списку каналів: {str(e)}")
    
    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.add_user_to_db(user_id)
        
        if self.user_notifications.get(user_id, True):
            await update.message.reply_text(f"Ти написав: {update.message.text}")
        else:
            await update.message.reply_text("Сповіщення вимкнено. Використай /on щоб увімкнути.")
    
    async def send_startup_message(self, app):
        """Відправляє повідомлення про запуск всім користувачам"""
        try:
            users_db = self.load_users_db()
            success_count = 0
            fail_count = 0
            
            logger.info(f"Спроба відправити повідомлення про запуск {len(users_db['users'])} користувачам")
            
            for user_id in users_db["users"]:
                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text="Бот був перезапущений. Система працює у штатному режимі!"
                    )
                    success_count += 1
                    logger.info(f"Повідомлення про запуск відправлено до {user_id}")
                except Exception as e:
                    fail_count += 1
                    error_msg = str(e).lower()
                    logger.warning(f"Не вдалося відправити повідомлення до {user_id}: {error_msg}")
                    
                    # Видаляємо користувача з бази у випадку певних помилок
                    if ("chat not found" in error_msg or 
                        "bot was blocked" in error_msg or 
                        "user is deactivated" in error_msg):
                        if user_id in users_db["users"]:
                            users_db["users"].remove(user_id)
                            logger.info(f"Користувача {user_id} видалено з бази через помилку: {error_msg}")
            
            # Зберігаємо оновлену базу тільки якщо були зміни
            if fail_count > 0:
                self.save_users_db(users_db)
            
            logger.info(f"Повідомлення про запуск: успішно - {success_count}, невдало - {fail_count}")
            
            # Відправляємо звіт адміну, якщо вказано в конфігурації
            if self.admin_chat_id:
                try:
                    target_chats = self.config_data.get('TargetChats', '')
                    channel_count = len([id_str.strip() for id_str in target_chats.split(',') if id_str.strip()])
                    
                    await app.bot.send_message(
                        chat_id=self.admin_chat_id,
                        text=f"Бот запущений\n\n"
                             f"Статистика запуску:\n"
                             f"•Користувачів: {len(users_db['users'])}\n"
                             f"•Відправлено: {success_count}\n"
                             f"•Невдало: {fail_count}\n"
                             f"•Каналів: {channel_count}"
                    )
                except Exception as e:
                    logger.error(f"Помилка при відправці звіту адміну: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Критична помилка при відправці повідомлень про запуск: {str(e)}")
    
    def analyze_message_with_patterns(self, message_text, channel_id=None):
        """
        Аналізує повідомлення за заданими патернами
        Повертає список знайдених відповідностей та відповідне повідомлення
        """
        if not message_text or not self.message_patterns:
            return [], None
        
        results = []
        notification_message = None
        
        try:
            # Додаємо інформацію про канал до повідомлення
            channel_info = f" (канал {channel_id})" if channel_id else ""
            
            # Перевірка для any_of (будь-яке зі слів)
            if 'any_of' in self.message_patterns:
                pattern_config = self.message_patterns['any_of']
                keywords = pattern_config.get('keywords', [])
                found_words = []
                
                for word in keywords:
                    if re.search(rf'\b{re.escape(word)}\b', message_text, re.IGNORECASE):
                        found_words.append(word)
                
                if found_words:
                    results.append(f"any_of: {found_words}")
                    if not notification_message:  # Пріоритет першого знайденого патерну
                        message_template = pattern_config.get('message', 'Знайдено слова: {found_words}')
                        notification_message = message_template.format(
                            found_words=', '.join(found_words),
                            message_preview=message_text[:300] + ('...' if len(message_text) > 300 else ''),
                            channel_info=channel_info
                        )
            
            # Перевірка для all_of (всі слова)
            if 'all_of' in self.message_patterns:
                pattern_config = self.message_patterns['all_of']
                keywords = pattern_config.get('keywords', [])
                found_all = True
                found_words = []
                
                for word in keywords:
                    if re.search(rf'\b{re.escape(word)}\b', message_text, re.IGNORECASE):
                        found_words.append(word)
                    else:
                        found_all = False
                
                if found_all and keywords:  # Перевіряємо, що список слів не порожній
                    results.append(f"all_of: {found_words}")
                    if not notification_message:
                        message_template = pattern_config.get('message', 'Знайдено всі слова: {found_words}')
                        notification_message = message_template.format(
                            found_words=', '.join(found_words),
                            message_preview=message_text[:300] + ('...' if len(message_text) > 300 else ''),
                            channel_info=channel_info
                        )
            
            # Перевірка для none_of (жодного зі слів)
            if 'none_of' in self.message_patterns:
                pattern_config = self.message_patterns['none_of']
                keywords = pattern_config.get('keywords', [])
                found_any = False
                avoided_words = []
                
                for word in keywords:
                    if re.search(rf'\b{re.escape(word)}\b', message_text, re.IGNORECASE):
                        found_any = True
                        avoided_words.append(word)
                
                if not found_any and keywords:  # Жодного слова не знайдено і список не порожній
                    results.append(f"none_of: уникнуто {keywords}")
                    if not notification_message:
                        message_template = pattern_config.get('message', 'Уникнуто слів: {avoided_words}')
                        notification_message = message_template.format(
                            avoided_words=', '.join(keywords),
                            message_preview=message_text[:300] + ('...' if len(message_text) > 300 else ''),
                            channel_info=channel_info
                        )
        
        except Exception as e:
            logger.error(f"Помилка при аналізі повідомлення: {str(e)}")
        
        return results, notification_message
    
    async def check_channel_messages(self):
        """Періодична перевірка всіх каналів та аналіз повідомлень за патернами"""
        app = None
        
        try:
            app = ApplicationBuilder().token(self.token).build()
            await app.initialize()
            await app.start()
        except Exception as e:
            logger.error(f"Помилка при ініціалізації app для check_channel_messages: {str(e)}")
            return
        
        check_interval = 300  # 5 хвилин між перевірками за замовчуванням
        
        while True:
            try:
                # Отримуємо повідомлення з усіх каналів
                result = await get_messages_from_all_channels(self.config_data)
                
                if not result['success']:
                    logger.error(f"Помилка отримання повідомлень: {result.get('error', 'Невідома помилка')}")
                    await asyncio.sleep(check_interval)
                    continue
                
                successful_channels = result.get('successful_channels', 0)
                total_channels = result.get('total_channels', 0)
                
                logger.info(f"Перевірено канали: {successful_channels}/{total_channels} успішно")
                
                # Обробляємо кожен канал
                for channel_result in result['results']:
                    if not channel_result['success']:
                        logger.error(f"Помилка в каналі {channel_result.get('channel_id', 'невідомо')}: {channel_result.get('error')}")
                        continue
                    
                    channel_id = channel_result['channel_id']
                    current_message = channel_result['message']
                    
                    # Пропускаємо порожні повідомлення
                    if current_message == "[Канал порожній]":
                        continue
                    
                    # Перевіряємо, чи змінилося повідомлення в цьому каналі
                    previous_message = self.previous_messages.get(channel_id)
                    
                    if previous_message is not None and current_message == previous_message:
                        logger.debug(f"Повідомлення в каналі {channel_id} не змінилось, пропускаємо обробку")
                        continue
                    
                    # Оновлюємо останнє повідомлення для цього каналу
                    self.previous_messages[channel_id] = current_message
                    
                    # Аналізуємо повідомлення за патернами
                    found_patterns, notification_message = self.analyze_message_with_patterns(current_message, channel_id)
                    
                    print("\n" + "="*60)
                    print(f"Новий пост з каналу {channel_id} (довжина: {len(current_message)} символів):")
                    print("-"*60)
                    print(current_message[:500] + ("..." if len(current_message) > 500 else ""))
                    print("-"*60)
                    
                    if found_patterns:
                        print(f"Знайдені патерни: {', '.join(found_patterns)}")
                        if notification_message:
                            # Надсилаємо сповіщення користувачам
                            success_count, fail_count = await self.send_notification_to_users(app, notification_message)
                            print(f" Відправлено сповіщень: {success_count} успішно, {fail_count} невдало")
                    else:
                        print("Патерни не знайдені")
                    print("="*60 + "\n")
                
                # Збільшуємо інтервал перевірки після кожної ітерації
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Помилка при перевірці каналів: {str(e)}")
                # Збільшуємо інтервал при помилках
                await asyncio.sleep(check_interval * 2)
    
    async def run(self):
        """Запуск бота"""
        try:
            self.application = ApplicationBuilder().token(self.token).build()

            self.application.add_handler(CommandHandler("on", self.turn_on))
            self.application.add_handler(CommandHandler("off", self.turn_off))
            self.application.add_handler(CommandHandler("status", self.status))
            self.application.add_handler(CommandHandler("channels", self.channels))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo))

            logger.info("Бот запускається...")
            
            await self.application.initialize()
            await self.application.start()
            
            await self.send_startup_message(self.application)
            
            asyncio.create_task(self.check_channel_messages())
            
            logger.info("Бот успішно запущений. Очікування повідомлень...")
            await self.application.updater.start_polling()
            
            while True:
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Помилка при запуску бота: {str(e)}")
        finally:
            if self.application:
                await self.application.stop()
                logger.info("Бот зупинений")