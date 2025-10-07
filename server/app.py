from . import create_app

app = create_app()


if __name__ == "__main__":
    # TODO: Configure host, port, and debug options via environment variables
    app.run(host="0.0.0.0", port=5000, debug=app.config.get("DEBUG", False))
