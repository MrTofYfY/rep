import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import aiohttp
import g4f

# ----------------- Load .env -----------------
load_dotenv()
BOT_TOKEN = os.getenv("TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "mellfreezy")
IMG_API_KEY = os.getenv("IMG_API_KEY")  # <- DeepAI ключ

if not BOT_TOKEN:
    raise RuntimeError("TOKEN не задан в .env или в переменных окружения")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ----------------- Access control -----------------
allowed_users = set([ADMIN_USERNAME])

def is_allowed(username):
    return username in allowed_users

# ----------------- Keyboards -----------------
kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("🧠 Chat"), KeyboardButton("🖼️ Image")]],
    resize_keyboard=True
)

# ----------------- Handlers -----------------
@dp.message(CommandStart())
async def start(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    # Проверка наличия ключа DeepAI
    status = "DeepAI: ключ установлен" if IMG_API_KEY else "DeepAI: ключ НЕ установлен"
    await m.answer(f"Привет! {status}", reply_markup=kb)

# ----------------- Chat (g4f) -----------------
@dp.message(lambda msg: msg.text == "🧠 Chat")
async def chat_mode(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    await m.answer("Напиши сообщение для модели:")
    dp.message.register(handle_chat, lambda mm: mm.from_user.username == m.from_user.username)

async def handle_chat(m: types.Message):
    dp.message.unregister(handle_chat)
    prompt = m.text.strip()
    await m.answer("⌛ Модель думает...")
    try:
        response = g4f.ChatCompletion.create(
            model="gpt-3.5-turbo",
            provider="You",   # бесплатный провайдер
            messages=[{"role":"user","content":prompt}]
        )
        await m.answer(response)
    except Exception as e:
        await m.answer(f"Ошибка модели: {e}")

# ----------------- Image (DeepAI) -----------------
@dp.message(lambda msg: msg.text == "🖼️ Image")
async def image_mode(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    if not IMG_API_KEY:
        await m.answer("⚠️ DeepAI ключ не настроен. Добавь IMG_API_KEY в .env или в переменные окружения Render.")
        return
    await m.answer("Отправь промпт для генерации изображения:")
    dp.message.register(handle_image, lambda mm: mm.from_user.username == m.from_user.username)

async def handle_image(m: types.Message):
    dp.message.unregister(handle_image)
    prompt = m.text.strip()
    await m.answer("🎨 Генерация изображения...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepai.org/api/text2img",
                data={"text": prompt},
                headers={"api-key": IMG_API_KEY},
                timeout=120
            ) as resp:
                if resp.status != 200:
                    txt = await resp.text()
                    await m.answer(f"Ошибка от DeepAI: {resp.status}\n{txt}")
                    return
                data = await resp.json()
                img_url = data.get("output_url") or data.get("output", {}).get("url")
                if img_url:
                    await m.answer_photo(photo=img_url)
                else:
                    await m.answer("DeepAI вернул неожиданный ответ (нет output_url).")
    except asyncio.TimeoutError:
        await m.answer("⏳ Таймаут при обращении к DeepAI.")
    except Exception as e:
        await m.answer(f"Ошибка генерации картинки: {e}")

# ----------------- Fallback -----------------
@dp.message()
async def fallback(m: types.Message):
    if is_allowed(m.from_user.username):
        await m.reply("Используй кнопки 🧠 Chat или 🖼️ Image (или /start).")

# ----------------- Run -----------------
async def main():
    print("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
