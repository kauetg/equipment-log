import os

from app import create_app

app = create_app()
# Nome próprio pro cookie: guardiola e equipment log rodam no mesmo localhost em dev
app.config["SESSION_COOKIE_NAME"] = "equipment_log_session"

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5006)))
