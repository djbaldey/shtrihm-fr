import logging
from logging.handlers import RotatingFileHandler


def setup_logger(log_name):
    # my_path = Path.cwd()
    # log_name = my_path / 'test.log'
    # log_name = 'working_area/eais_logs.log'
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [%(levelname)s] -  %(name)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            RotatingFileHandler(log_name, maxBytes=10485760, backupCount=3)
        ]
    )


def set_global_logging_level(level):
    logging.getLogger().setLevel(level)


def get_logger(name):
    return logging.getLogger(name)
