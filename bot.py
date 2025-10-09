import os
import asyncio
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import base64

# ----------------- Load .env -----------------
load_dotenv()
BOT_TOKEN = os.getenv("TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "mellfreezy")
CHAT_API_URL = os.getenv("CHAT_API_URL", "http://127.0.0.1:5000/generate")
IMG_API_URL = os.getenv("IMG_API_URL", "http://127.0.0.1:7860/sdapi/v1/txt2img")

if not BOT_TOKEN:
    raise RuntimeError("TOKEN not set in .env")

# ----------------- Logging -----------------
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ----------------- Access control -----------------
ACCESS_FILE = Path("access.json")
if ACCESS_FILE.exists():
    allowed_users = set(json.load(open(ACCESS_FILE))["allowed"])
else:
    allowed_users = set([ADMIN_USERNAME])

def save_allowed():
    with open(ACCESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"allowed": list(allowed_users)}, f, ensure_ascii=False, indent=2)

def is_allowed(username):
    return username in allowed_users

# ----------------- Keyboards -----------------
admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🧠 Chat"), KeyboardButton("🖼️ Image")],
        [KeyboardButton("✅ Grant"), KeyboardButton("❌ Revoke")]
    ], resize_keyboard=True
)
user_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("🧠 Chat"), KeyboardButton("🖼️ Image")]],
    resize_keyboard=True
)

# ----------------- Concurrency limit -----------------
semaphore = asyncio.Semaphore(2)  # максимум 2 одновременных запроса

# ----------------- Handlers -----------------
@dp.message(CommandStart())
async def start(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    kb = admin_kb if m.from_user.username == ADMIN_USERNAME else user_kb
    await m.answer("Привет! Выбери режим.", reply_markup=kb)

@dp.message(lambda msg: msg.text == "✅ Grant")
async def grant_step(m: types.Message):
    if m.from_user.username != ADMIN_USERNAME:
        await m.answer("⛔ Только админ.")
        return
    await m.answer("Отправь юзернейм (без @) для выдачи доступа.")
    dp.message.register(handle_grant, lambda mm: True)

async def handle_grant(m: types.Message):
    username = m.text.strip().lstrip("@")
    if username:
        allowed_users.add(username)
        save_allowed()
        await m.answer(f"✅ @{username} добавлен.")
    dp.message.unregister(handle_grant)

@dp.message(lambda msg: msg.text == "❌ Revoke")
async def revoke_step(m: types.Message):
    if m.from_user.username != ADMIN_USERNAME:
        await m.answer("⛔ Только админ.")
        return
    await m.answer("Отправь юзернейм (без @) для удаления доступа.")
    dp.message.register(handle_revoke, lambda mm: True)

async def handle_revoke(m: types.Message):
    username = m.text.strip().lstrip("@")
    if username in allowed_users:
        allowed_users.remove(username)
        save_allowed()
        await m.answer(f"❌ @{username} удалён.")
    else:
        await m.answer("Пользователь не найден.")
    dp.message.unregister(handle_revoke)

# ----------------- Chat -----------------
@dp.message(lambda msg: msg.text == "🧠 Chat")
async def enter_chat(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    await m.answer("Напиши сообщение для модели (ответит текстом).")
    dp.message.register(handle_chat, lambda mm: mm.from_user.username == m.from_user.username)

async def handle_chat(m: types.Message):
    dp.message.unregister(handle_chat)
    prompt = m.text.strip()
    await m.answer("⌛ Запрос к модели...")
    async with semaphore:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"prompt": prompt, "max_new_tokens": 512}
                async with session.post(CHAT_API_URL, json=payload, timeout=120) as resp:
                    if resp.status != 200:
                        txt = await resp.text()
                        await m.answer(f"Ошибка chat-сервера: {resp.status}\n{txt}")
                        return
                    data = await resp.json()
                    text = data.get("text") or data.get("generated_text") or str(data)
                    await m.answer(text)
        except asyncio.TimeoutError:
            await m.answer("⏳ Таймаут при обращении к chat-серверу.")
        except Exception as e:
            await m.answer(f"Ошибка chat-сервера: {e}")

# ----------------- Image -----------------
@dp.message(lambda msg: msg.text == "🖼️ Image")
async def enter_image(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    await m.answer("Отправь промпт для генерации изображения.")
    dp.message.register(handle_image, lambda mm: mm.from_user.username == m.from_user.username)

async def handle_image(m: types.Message):
    dp.message.unregister(handle_image)
    prompt = m.text.strip()
    await m.answer("🎨 Генерация изображения...")
    async with semaphore:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "prompt": prompt,
                    "steps": 20,
                    "width": 512,
                    "height": 512,
                    "sampler_name": "Euler a"
                }
                async with session.post(IMG_API_URL, json=payload, timeout=300) as resp:
                    if resp.status != 200:
                        txt = await resp.text()
                        await m.answer(f"Ошибка image-сервера: {resp.status}\n{txt}")
                        return
                    data = await resp.json()
                    images = data.get("images") or []
                    if not images:
                        await m.answer("Пустой ответ от image-сервера.")
                        return
                    img_bytes = base64.b64decode(images[0])
                    await m.answer_photo(photo=img_bytes)
        except asyncio.TimeoutError:
            await m.answer("⏳ Таймаут при генерации картинки.")
        except Exception as e:
            await m.answer(f"Ошибка генерации картинки: {e}")

# ----------------- Fallback -----------------
@dp.message()
async def fallback(m: types.Message):
    if is_allowed(m.from_user.username):
        await m.reply("Используй кнопки: 🧠 Chat или 🖼️ Image (или /start).")

# ----------------- Run -----------------
async def main():
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
