import xml.etree.ElementTree as ET
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

class ConfigReader:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigReader, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        try:
            config_path = Path(__file__).parent / "bot.config"
            if not config_path.exists():
                raise FileNotFoundError(f"Configuration file not found at {config_path}")
            
            tree = ET.parse(config_path)
            root = tree.getroot()
            app_settings = root.find(".//appSettings")
            if app_settings is None:
                raise ValueError("appSettings section not found in config file")
            
            # Створюємо словник для зберігання всіх конфігураційних даних
            self.config_data = {}
                
            for elem in app_settings.findall("add"):
                key = elem.get('key')
                value = elem.get('value')
                if key is None or value is None:
                    continue
                
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                elif value.isdigit():
                    value = int(value)
                elif key == 'MessagePatterns':
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        logger.error(f"Помилка парсингу JSON для MessagePatterns: {value}")
                        value = {}
                
                # Зберігаємо значення як атрибут і в словнику
                setattr(self, key, value)
                self.config_data[key] = value
            
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration: {str(e)}")
    
    def get_config_dict(self):
        """Повертає всю конфігурацію у вигляді словника"""
        return self.config_data.copy()