import os
import logging
from datetime import datetime

class Logger:
    _instance = None

    @staticmethod
    def get_logger(name="AppLogger"):
        # Configure root logger once
        if not getattr(Logger, "_is_configured", False):
            Logger._setup_handlers()
            Logger._is_configured = True
        
        return logging.getLogger(name)

    @staticmethod
    def _setup_handlers():
        # Get root logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # Clear existing handlers to avoid duplicates
        if logger.handlers:
            logger.handlers.clear()

        # Console Handler
        c_handler = logging.StreamHandler()
        c_handler.setLevel(logging.INFO)
        c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)

        # File Handler
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            f_handler = logging.FileHandler(os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log"), encoding='utf-8')
            f_handler.setLevel(logging.INFO)
            f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            f_handler.setFormatter(f_format)
            logger.addHandler(f_handler)
        except Exception as e:
            print(f"Failed to setup file logging: {e}")

