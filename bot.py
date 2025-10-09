import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Для модели текста
from gpt4all import GPT4All

# Для генерации изображений
from diffusers import StableDiffusionPipeline
import torch
from PIL import Image
import io

# ----------------- Load .env -----------------
load_dotenv()
BOT_TOKEN = os.getenv("TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "mellfreezy")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ----------------- Access -----------------
allowed_users = set([ADMIN_USERNAME])

def is_allowed(username):
    return username in allowed_users

# ----------------- Keyboards -----------------
kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("🧠 Chat"), KeyboardButton("🖼️ Image")]],
    resize_keyboard=True
)

# ----------------- Initialize models -----------------
print("Загружаем GPT4All (текстовая модель)...")
chat_model = GPT4All("gpt4all-lora-quantized")  # модель скачивается автоматически при первом запуске

print("Загружаем Stable Diffusion (CPU)...")
pipe = StableDiffusionPipeline.from_pretrained(
    "runwayml/stable-diffusion-v1-5",
    torch_dtype=torch.float32
)
pipe = pipe.to("cpu")

# ----------------- Handlers -----------------
@dp.message(CommandStart())
async def start(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    await m.answer("Привет! Выбери режим:", reply_markup=kb)

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
        response = chat_model.generate(prompt)
        await m.answer(response)
    except Exception as e:
        await m.answer(f"Ошибка модели: {e}")

@dp.message(lambda msg: msg.text == "🖼️ Image")
async def image_mode(m: types.Message):
    if not is_allowed(m.from_user.username):
        await m.answer("⛔ Нет доступа.")
        return
    await m.answer("Отправь промпт для генерации изображения:")
    dp.message.register(handle_image, lambda mm: mm.from_user.username == m.from_user.username)

async def handle_image(m: types.Message):
    dp.message.unregister(handle_image)
    prompt = m.text.strip()
    await m.answer("🎨 Генерация изображения...")
    try:
        image = pipe(prompt, height=512, width=512).images[0]
        bio = io.BytesIO()
        image.save(bio, format="PNG")
        bio.seek(0)
        await m.answer_photo(photo=bio)
    except Exception as e:
        await m.answer(f"Ошибка генерации изображения: {e}")

# ----------------- Fallback -----------------
@dp.message()
async def fallback(m: types.Message):
    if is_allowed(m.from_user.username):
        await m.reply("Используй кнопки 🧠 Chat или 🖼️ Image (или /start).")

# ----------------- Run -----------------
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
