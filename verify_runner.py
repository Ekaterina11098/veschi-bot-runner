"""Manual connection check. No source data or credentials are logged."""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

def request(url, headers=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def main():
    for key in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "ADVERTISING_TELEGRAM_BOT_TOKEN", "WB_TOKEN_1"):
        if not os.getenv(key):
            print("Missing required setting: " + key)
            return 1
    key = os.environ["SUPABASE_SECRET_KEY"]
    headers = {"apikey": key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = "Bearer " + key
    base = os.environ["SUPABASE_URL"].rstrip("/")
    chats = request(base + "/rest/v1/advertising_telegram_chat?is_active=eq.true&select=chat_id&limit=2", headers)
    if len(chats) != 1:
        print("Advertising destination must have exactly one active registration.")
        return 1
    print("Database and advertising destination verified.")
    token = os.environ["ADVERTISING_TELEGRAM_BOT_TOKEN"]
    api = "https://api.telegram.org/bot" + token
    me = request(api + "/getMe")
    if not me.get("ok"):
        print("Advertising bot verification failed.")
        return 1
    request(api + "/getChat", {"Content-Type": "application/json"}, {"chat_id": chats[0]["chat_id"]})
    print("Advertising bot access to destination verified.")
    # Check the ordinary WB token for both feedback categories without changing answers.
    for category in ("feedbacks", "questions"):
        request("https://feedbacks-api.wildberries.ru/api/v1/" + category + "?isAnswered=false&take=1&skip=0",
                {"Authorization": os.environ["WB_TOKEN_1"]})
    print("Ordinary WB token can read reviews and questions.")
    result = request(api + "/sendMessage", {"Content-Type": "application/json"},
                     {"chat_id": chats[0]["chat_id"], "text": "✅ Тест рекламного бота из нового репозитория GitHub. Доступ к данным и отправка в рекламную беседу проверены. Это проверка доставки; расписание ещё подключается."})
    if not result.get("ok"):
        print("Advertising test delivery failed.")
        return 1
    print("Advertising test message accepted by Telegram.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as error:
        print("Connection check failed: HTTP " + str(error.code) + ". No automatic resend.")
        sys.exit(1)
    except Exception as error:
        print("Connection check failed: " + type(error).__name__ + ". No automatic resend.")
        sys.exit(1)
