"""Generate local secrets once. Deliberately refuses to overwrite existing .env."""
import secrets
from pathlib import Path

path = Path(__file__).resolve().parents[1] / ".env"
postgres_password = secrets.token_hex(24)
with path.open("x", encoding="utf-8") as file:
    file.write(
        f"POSTGRES_PASSWORD={postgres_password}\n"
        f"JWT_SECRET={secrets.token_hex(32)}\n"
        f"DEMO_PASSWORD={secrets.token_urlsafe(18)}\n"
        f"ZUP_API_TOKEN={secrets.token_hex(32)}\n"
        f"DOCUMENTOLOG_API_KEY={secrets.token_hex(32)}\n"
        "DOCUMENTOLOG_MODE=mock\n"
        "ZUP_MODE=mock\n"
        "ZUP_AUTH_TYPE=bearer\n"
        f"DATABASE_URL=postgresql+psycopg://jana:{postgres_password}@127.0.0.1:5432/jana\n"
    )
path.chmod(0o600)
print("Создан .env. Демо-пароль смотрите локально в DEMO_PASSWORD; не отправляйте его в Git.")
