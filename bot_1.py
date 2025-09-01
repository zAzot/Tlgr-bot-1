from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import asyncio
import logging
import json
import os
import re
from pathlib import Path

from telegram_module import get_last_channel_message

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
            if self.user_notifications.get(user_id, True):  # Якщо сповіщення увімкнені
                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=message
                    )
                    success_count += 1
                    logger.info(f"Повідомлення відправлено до {user_id}")
                except Exception as e:
                    fail_count += 1
                    logger.warning(f"Не вдалося відправити повідomлення до {user_id}: {str(e)}")
                    if "Chat not found" in str(e) or "bot was blocked" in str(e).lower():
                        # Видаляємо користувача з бази, якщо чат не знайдено або бот заблокований
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
                    await app.bot.send_message(
                        chat_id=self.admin_chat_id,
                        text=f"Бот запущений. Повідомлення про запуск відправлено:\n Успішно: {success_count}\n Невдало: {fail_count}\n Всього користувачів: {len(users_db['users'])}"
                    )
                except Exception as e:
                    logger.error(f"Помилка при відправці звіту адміну: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Критична помилка при відправці повідомлень про запуск: {str(e)}")
    
    def analyze_message_with_patterns(self, message_text):
        """
        Аналізує повідомлення за заданими патернами
        Повертає список знайдених відповідностей та відповідне повідомлення
        """
        if not message_text or not self.message_patterns:
            return [], None
        
        results = []
        notification_message = None
        
        try:
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
                            message_preview=message_text[:300] + ('...' if len(message_text) > 300 else '')
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
                            message_preview=message_text[:300] + ('...' if len(message_text) > 300 else '')
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
                            message_preview=message_text[:300] + ('...' if len(message_text) > 300 else '')
                        )
        
        except Exception as e:
            logger.error(f"Помилка при аналізі повідомлення: {str(e)}")
        
        return results, notification_message
    
    async def check_channel_messages(self):
        """Періодична перевірка каналу та аналіз повідомлень за патернами"""
        previous_message = None
        app = None
        
        try:
            app = ApplicationBuilder().token(self.token).build()
            await app.initialize()
            await app.start()
        except Exception as e:
            logger.error(f"Помилка при ініціалізації app для check_channel_messages: {str(e)}")
            return
        
        while True:
            try:
                # Використовуємо config_data замість завантаження з файлу
                current_result = await get_last_channel_message(self.config_data)
                
                if not current_result['success']:
                    logger.error(f"Помилка отримання повідомлення: {current_result.get('error', 'Невідома помилка')}")
                    await asyncio.sleep(300)
                    continue
                    
                current_message = current_result['message']
                
                if previous_message is not None and current_message == previous_message:
                    logger.info("Повідомлення не змінилось, пропускаємо обробку")
                    await asyncio.sleep(300)
                    continue
                    
                previous_message = current_message
                
                # Аналізуємо повідомлення за патернами
                found_patterns, notification_message = self.analyze_message_with_patterns(current_message)
                
                print("\n" + "="*50)
                print(f" Нове повідомлення з каналу (довжина: {len(current_message)} символів):")
                print("-"*50)
                print(current_message[:500] + ("..." if len(current_message) > 500 else ""))
                print("-"*50)
                
                if found_patterns:
                    print(f" Знайдені патерни: {', '.join(found_patterns)}")
                    if notification_message:
                        # Надсилаємо сповіщення користувачам
                        await self.send_notification_to_users(app, notification_message)
                else:
                    print(" Патерни не знайдені")
                print("="*50 + "\n")
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Помилка при перевірці каналу: {str(e)}")
                await asyncio.sleep(60)
    
    async def run(self):
        """Запуск бота"""
        try:
            self.application = ApplicationBuilder().token(self.token).build()

            self.application.add_handler(CommandHandler("on", self.turn_on))
            self.application.add_handler(CommandHandler("off", self.turn_off))
            self.application.add_handler(CommandHandler("status", self.status))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo))

            logger.info("Бот запускається...")
            
            await self.application.initialize()
            await self.application.start()
            
            # Відправляємо повідomлення про запуск ВСІМ користувачам (незалежно від налаштувань сповіщень)
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