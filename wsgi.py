import time
import configparser
from fiscal_network import app
from waitress import serve
from logs import logger as log

log.setup_logger('fiscal.log')
logger = log.get_logger(__name__)
# Настройка логгирования
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# Чтение конфигурации
config = configparser.ConfigParser()
config.read('config/config.ini')

# Получение параметров хоста и порта из конфигурации
host = config.get('server', 'host', fallback='0.0.0.0')
port = config.getint('server', 'port', fallback=5000)

# host = '0.0.0.0'
# port = 5000

RETRY_DELAY = 1  # Время задержки перед повторной попыткой в секундах

if __name__ == "__main__":
    while True:
        logger.info(f"Запуск сервера на http://{host}:{port}")
        try:
            serve(app, host=host, port=port)
        except Exception as e:
            logger.error(f"Ошибка при запуске сервера: {e}")
            time.sleep(RETRY_DELAY)  # Задержка перед повторной попыткой
