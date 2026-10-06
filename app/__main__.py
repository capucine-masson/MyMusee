"""Lance le serveur : python -m app"""
import logging

import uvicorn

from . import config
from .main import app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=config.HOST, port=config.PORT)
