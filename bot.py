# main.py
import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
import openai
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# -----------------------
# Загрузка .env
# -----------------------
load_dotenv()  # прочитает .env из текущей директории

BOT_TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "mellfreezy")

if not BOT_TOKEN:
    raise RuntimeError("Не найден TOKEN в .env — установи TOKEN=тут_токен")
if not OPENAI_API_KEY:
    # мы разрешаем работать и без OpenAI (см. ниже), но предупреждаем
    print("WARN: OPENAI_API_KEY не найден в .env — генерация через OpenAI будет недоступна.")

# -----------------------
# Настройка OpenAI
# -----------------------
openai.api_key = OPENAI_API_KEY

# -----------------------
# Файлы и логирование
# -----------------------
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ACCESS_FILE = Path("access.json")

def load_allowed():
    if ACCESS_FILE.exists():
        try:
            with ACCESS_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("allowed", []))
        except Exception:
            return set([ADMIN_USERNAME])
    return set([ADMIN_USERNAME])

def save_allowed(allowed_set):
    data = {"allowed": list(allowed_set)}
    with ACCESS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

allowed_users = load_allowed()

# -----------------------
# Кнопки клавиатуры
# -----------------------
admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧠 ChatGPT"), KeyboardButton(text="🖼️ GPT Image")],
        [KeyboardButton(text="✅ Дать доступ"), KeyboardButton(text="❌ Удалить доступ")]
    ],
    resize_keyboard=True
)

user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧠 ChatGPT"), KeyboardButton(text="🖼️ GPT Image")]
    ],
    resize_keyboard=True
)

# -----------------------
# Утилиты
# -----------------------
def is_allowed(username: str | None) -> bool:
    if username is None:
        return False
    return username in allowed_users

# -----------------------
# Хендлеры
# -----------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    username = message.from_user.username
    if not is_allowed(username):
        await message.answer("⛔ У вас нет доступа к этому боту.")
        return

    if username == ADMIN_USERNAME:
        await message.answer("👑 Привет, Админ!", reply_markup=admin_kb)
    else:
        await message.answer("🤖 Привет! Я твой GPT бот.", reply_markup=user_kb)

# Простой режим: если пользователь нажал кнопку "ChatGPT" — просим ввести запрос
@dp.message(lambda m: m.text == "🧠 ChatGPT")
async def chatgpt_mode(message: types.Message):
    if not is_allowed(message.from_user.username):
        await message.answer("⛔ У вас нет доступа.")
        return
    await message.answer("✍️ Напиши запрос для ChatGPT (я отправлю его в OpenAI).")
    # следующий текст пользователя обработает universal_query

# Аналогично для картинок
@dp.message(lambda m: m.text == "🖼️ GPT Image")
async def image_mode(message: types.Message):
    if not is_allowed(message.from_user.username):
        await message.answer("⛔ У вас нет доступа.")
        return
    await message.answer("🖌️ Опиши картинку, которую нужно сгенерировать (коротко).")

# Управление доступом — доступны только админу
@dp.message(lambda m: m.text in {"✅ Дать доступ", "❌ Удалить доступ"})
async def access_control(message: types.Message):
    if message.from_user.username != ADMIN_USERNAME:
        await message.answer("⛔ Только админ может управлять доступом.")
        return

    if message.text == "✅ Дать доступ":
        await message.answer("Введите юзернейм (без @), которому дать доступ:")
        # следующий текст — grant step
        dp.message.register(grant_access_step, lambda m: True)
    else:
        await message.answer("Введите юзернейм (без @), у которого удалить доступ:")
        dp.message.register(remove_access_step, lambda m: True)

async def grant_access_step(message: types.Message):
    # ожидаем простой текст — юзернейм без @
    username = message.text.strip().lstrip("@")
    if not username:
        await message.answer("Неверный юзернейм.")
    else:
        allowed_users.add(username)
        save_allowed(allowed_users)
        await message.answer(f"✅ Доступ выдан пользователю @{username}")
    dp.message.unregister(grant_access_step)

async def remove_access_step(message: types.Message):
    username = message.text.strip().lstrip("@")
    if username in allowed_users:
        allowed_users.remove(username)
        save_allowed(allowed_users)
        await message.answer(f"❌ Доступ удалён у @{username}")
    else:
        await message.answer("⚠️ Такой пользователь не найден в списке.")
    dp.message.unregister(remove_access_step)

# Универсальный обработчик сообщения: если это текст и пользователь имеет доступ,
# решаем, это запрос в ChatGPT или генерация картинки по последней команде.
@dp.message()
async def universal_query(message: types.Message):
    username = message.from_user.username
    if not is_allowed(username):
        # игнорируем
        return

    text = message.text.strip()
    if not text:
        return

    # Решение: если сообщение начинается с "/img " — генерируем изображение,
    # иначе — отправляем в ChatGPT.
    if text.startswith("/img "):
        prompt = text[len("/img "):].strip()
        if not OPENAI_API_KEY:
            await message.answer("⚠️ OpenAI API ключ не настроен — генерация изображений недоступна.")
            return
        await message.answer("🎨 Генерирую изображение...")
        try:
            resp = openai.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="512x512"
            )
            # Ответ может быть в resp.data[0].url
            img_url = resp.data[0].url
            await message.answer_photo(photo=img_url, caption="Готово!")
        except Exception as e:
            await message.answer(f"Ошибка при генерации изображения: {e}")
    else:
        # ChatGPT
        if not OPENAI_API_KEY:
            await message.answer("⚠️ OpenAI API ключ не настроен — чат недоступен.")
            return
        await message.answer("⌛ Думаю...")
        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": text}]
            )
            reply = response.choices[0].message.content
            await message.answer(reply)
        except Exception as e:
            await message.answer(f"Ошибка при обращении к OpenAI: {e}")

# -----------------------
# Запуск
# -----------------------
async def main():
    print("Бот запущен. Убедись, что .env заполнен и .gitignore содержит .env")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
