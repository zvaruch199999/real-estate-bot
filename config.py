import os

def _req(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"{name} не заданий (Railway Variables)")
    return val

BOT_TOKEN = _req("BOT_TOKEN")

# В Railway змінні: GROUP_CHAT_ID = -100xxxxxxxxxx
GROUP_CHAT_ID = int(_req("GROUP_CHAT_ID"))

# (опційно) якщо хочеш обмежити доступ тільки собі:
# ADMIN_USER_IDS="1057216609,123..."
ADMIN_USER_IDS = [int(x) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip().isdigit()]
