from . import create_app
from flask_cors import CORS

app = create_app()

# Enable CORS for API routes
CORS(app, resources={r"/api/*": {"origins": "*"}})


if __name__ == "__main__":
    # TODO: Configure host, port, and debug options via environment variables
    app.run(host="0.0.0.0", port=5000, debug=app.config.get("DEBUG", False))
