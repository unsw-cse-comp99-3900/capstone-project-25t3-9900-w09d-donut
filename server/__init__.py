from flask import Flask

from .config.settings import load_config
from .controllers.api_controller import api_blueprint


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(load_config(config_name))

    # TODO: Register additional blueprints (auth, health checks, webhooks)
    app.register_blueprint(api_blueprint, url_prefix="/api")

    # TODO: Initialize database, vector store, and external service clients here

    return app
