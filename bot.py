import os
import json
import asyncio
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ==========================================================
#                    НАСТРОЙКИ И ФАЙЛЫ
# ==========================================================
load_dotenv()
BOT_TOKEN = os.getenv("TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "mellfreezy")
IMG_API_KEY = os.getenv("IMG_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("❌ В .env не указан TOKEN")

ACCESS_FILE = "access.json"

def load_access():
    if os.path.exists(ACCESS_FILE):
        with open(ACCESS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return {ADMIN_USERNAME}

def save_access():
    with open(ACCESS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(allowed_users), f, ensure_ascii=False, indent=2)

allowed_users = load_access()

def is_admin(username: str) -> bool:
    return username == ADMIN_USERNAME

def is_allowed(username: str) -> bool:
    return username in allowed_users

# ==========================================================
#                       СОСТОЯНИЯ FSM
# ==========================================================
class ChatState(StatesGroup):
    waiting_for_text = State()

class ImageState(StatesGroup):
    waiting_for_prompt = State()

class AccessState(StatesGroup):
    give_username = State()
    remove_username = State()

# ==========================================================
#                      КЛАВИАТУРЫ
# ==========================================================
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧠 Chat"), KeyboardButton(text="🖼️ Image")]
    ],
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧠 Chat"), KeyboardButton(text="🖼️ Image")],
        [KeyboardButton(text="👤 Дать доступ"), KeyboardButton(text="🚫 Забрать доступ")]
    ],
    resize_keyboard=True
)

# ==========================================================
#                        БОТ
# ==========================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==========================================================
#                        /start
# ==========================================================
@dp.message(CommandStart())
async def start(message: types.Message):
    username = message.from_user.username
    if not is_allowed(username):
        await message.answer("⛔ У тебя нет доступа к этому боту.")
        return

    kb = admin_kb if is_admin(username) else user_kb
    await message.answer(f"👋 Привет, {message.from_user.first_name}!", reply_markup=kb)

# ==========================================================
#                    АДМИН - ДОСТУП
# ==========================================================
@dp.message(F.text == "👤 Дать доступ")
async def give_access_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.username):
        await message.answer("⛔ Только админ может это делать.")
        return
    await message.answer("✍️ Введите юзернейм (без @), кому дать доступ:")
    await state.set_state(AccessState.give_username)

@dp.message(AccessState.give_username)
async def give_access_finish(message: types.Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    await state.clear()
    if username in allowed_users:
        await message.answer(f"⚠️ @{username} уже имеет доступ.")
    else:
        allowed_users.add(username)
        save_access()
        await message.answer(f"✅ Доступ для @{username} выдан!")

@dp.message(F.text == "🚫 Забрать доступ")
async def remove_access_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.username):
        await message.answer("⛔ Только админ может это делать.")
        return
    await message.answer("✍️ Введите юзернейм (без @), у кого забрать доступ:")
    await state.set_state(AccessState.remove_username)

@dp.message(AccessState.remove_username)
async def remove_access_finish(message: types.Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    await state.clear()

    if username == ADMIN_USERNAME:
        await message.answer("❌ Нельзя удалить самого админа!")
        return

    if username in allowed_users:
        allowed_users.remove(username)
        save_access()
        await message.answer(f"🚫 Доступ @{username} удалён.")
    else:
        await message.answer(f"⚠️ @{username} не найден.")

# ==========================================================
#                       CHAT
# ==========================================================
@dp.message(F.text == "🧠 Chat")
async def chat_start(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.username):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("💬 Напиши сообщение для нейросети:")
    await state.set_state(ChatState.waiting_for_text)

@dp.message(ChatState.waiting_for_text)
async def chat_process(message: types.Message, state: FSMContext):
    await state.clear()
    prompt = message.text.strip()
    await message.answer("⌛ Думаю...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepai.org/api/text-generator",
                data={"text": prompt},
                headers={"api-key": IMG_API_KEY}
            ) as resp:
                data = await resp.json()
                output = data.get("output", "⚠️ Ошибка при обработке текста.")
                await message.answer(output)
    except Exception as e:
        await message.answer(f"❌ Ошибка при работе с API: {e}")

# ==========================================================
#                       IMAGE
# ==========================================================
@dp.message(F.text == "🖼️ Image")
async def image_start(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.username):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("🎨 Введи описание изображения:")
    await state.set_state(ImageState.waiting_for_prompt)

@dp.message(ImageState.waiting_for_prompt)
async def image_process(message: types.Message, state: FSMContext):
    await state.clear()
    prompt = message.text.strip()
    await message.answer("🖌️ Генерация изображения...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepai.org/api/text2img",
                data={"text": prompt},
                headers={"api-key": IMG_API_KEY},
                timeout=120
            ) as resp:
                data = await resp.json()
                img_url = data.get("output_url")
                if img_url:
                    await message.answer_photo(photo=img_url)
                else:
                    await message.answer("⚠️ Не удалось создать изображение.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при работе с API: {e}")

# ==========================================================
#                   ОБРАБОТКА ПРОЧЕГО
# ==========================================================
@dp.message()
async def fallback(message: types.Message):
    username = message.from_user.username
    if not is_allowed(username):
        await message.answer("⛔ Нет доступа.")
        return

    kb = admin_kb if is_admin(username) else user_kb
    await message.answer("Выбери действие на клавиатуре 👇", reply_markup=kb)

# ==========================================================
#                       ЗАПУСК
# ==========================================================
async def main():
    print("✅ Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
