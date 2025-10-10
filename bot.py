import os
import json
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

# ==========================================
#              НАСТРОЙКИ
# ==========================================
load_dotenv()  # Загружаем переменные из .env

BOT_TOKEN = os.getenv("TOKEN")  # Токен телеграм-бота
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "mellfreezy")
HF_API_KEY = os.getenv("HF_API_KEY")  # Токен HuggingFace

if not BOT_TOKEN or not HF_API_KEY:
    raise RuntimeError("❌ В .env не указан TOKEN или HF_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ACCESS_FILE = "access.json"

# ==========================================
#              ДОСТУПЫ
# ==========================================
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

# ==========================================
#                FSM
# ==========================================
class ChatState(StatesGroup):
    waiting_for_text = State()

class AccessState(StatesGroup):
    give_username = State()
    remove_username = State()

# ==========================================
#             КЛАВИАТУРЫ
# ==========================================
user_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🧠 Чат")]],
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧠 Чат")],
        [KeyboardButton(text="👤 Дать доступ"), KeyboardButton(text="🚫 Забрать доступ")]
    ],
    resize_keyboard=True
)

# ==========================================
#                /START
# ==========================================
@dp.message(CommandStart())
async def start(message: types.Message):
    username = message.from_user.username
    if not is_allowed(username):
        await message.answer("⛔ У тебя нет доступа к этому боту.")
        return

    kb = admin_kb if is_admin(username) else user_kb
    await message.answer(
        f"💡 Привет, {message.from_user.first_name}!\n\n"
        f"Я — <b>LuminAI</b>, твой интеллектуальный собеседник. ✨\n\n"
        f"Выбери действие ниже 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

# ==========================================
#              ЧАТ РЕЖИМ
# ==========================================
@dp.message(F.text == "🧠 Чат")
async def start_chat(message: types.Message, state: FSMContext):
    username = message.from_user.username
    if not is_allowed(username):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("💬 Отправь сообщение, и LuminAI ответит тебе:")
    await state.set_state(ChatState.waiting_for_text)

@dp.message(ChatState.waiting_for_text)
async def handle_chat(message: types.Message, state: FSMContext):
    user_text = message.text.strip()
    await message.answer("✨ Думаю над ответом...")
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {HF_API_KEY}"}
            payload = {"inputs": user_text}
            async with session.post(
                "https://api-inference.huggingface.co/models/microsoft/DialoGPT-small",
                headers=headers,
                json=payload,
                timeout=60
            ) as resp:
                if resp.status != 200:
                    await message.answer(f"⚠️ Ошибка API: {resp.status}")
                    return
                result = await resp.json()
                if isinstance(result, dict) and "error" in result:
                    await message.answer(f"⚠️ Ошибка модели: {result['error']}")
                elif isinstance(result, list) and "generated_text" in result[0]:
                    reply = result[0]["generated_text"]
                    await message.answer(reply)
                else:
                    await message.answer(str(result))
    except Exception as e:
        await message.answer(f"❌ Ошибка при генерации: {e}")
    await state.clear()

# ==========================================
#           ДАТЬ / УДАЛИТЬ ДОСТУП
# ==========================================
@dp.message(F.text == "👤 Дать доступ")
async def give_access_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.username):
        await message.answer("⛔ Только админ может это делать.")
        return
    await message.answer("🔑 Введи @username, кому дать доступ:")
    await state.set_state(AccessState.give_username)

@dp.message(AccessState.give_username)
async def give_access_finish(message: types.Message, state: FSMContext):
    username = message.text.replace("@", "").strip()
    allowed_users.add(username)
    save_access()
    await message.answer(f"✅ Пользователь @{username} теперь имеет доступ.")
    await state.clear()

@dp.message(F.text == "🚫 Забрать доступ")
async def remove_access_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.username):
        await message.answer("⛔ Только админ может это делать.")
        return
    await message.answer("❗ Введи @username, у которого нужно забрать доступ:")
    await state.set_state(AccessState.remove_username)

@dp.message(AccessState.remove_username)
async def remove_access_finish(message: types.Message, state: FSMContext):
    username = message.text.replace("@", "").strip()
    if username in allowed_users:
        allowed_users.remove(username)
        save_access()
        await message.answer(f"🚫 Доступ пользователя @{username} удалён.")
    else:
        await message.answer(f"⚠️ Пользователь @{username} не найден в списке.")
    await state.clear()

# ==========================================
#               ЗАПУСК
# ==========================================
async def main():
    print("🤖 LuminAI запущен и готов к работе.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
