import os
import tempfile
import subprocess
import shutil
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from PIL import Image
from dotenv import load_dotenv
import pyzipper
import rarfile

# === Загрузка токена из .env ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# === Форматы ===
FORMAT_OPTIONS = {
    'image': ['jpg', 'jpeg', 'png', 'webp', 'svg'],
    'video': ['mp4', 'avi', 'webm', 'mov'],
    'audio': ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a'],
    'document': ['pdf', 'txt', 'docx'],
    'archive': ['zip', 'rar']
}

# === Хранилище временных файлов ===
user_file_store = {}

# === Определение типа файла ===
def detect_type(filename: str):
    ext = filename.split('.')[-1].lower()
    if ext in ['jpg', 'jpeg', 'png', 'webp', 'svg']:
        return 'image'
    elif ext in ['mp4', 'avi', 'mov', 'webm']:
        return 'video'
    elif ext in ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a']:
        return 'audio'
    elif ext in ['pdf', 'docx', 'txt']:
        return 'document'
    elif ext in ['zip', 'rar']:
        return 'archive'
    else:
        return 'unknown'

# === Конвертация через ffmpeg ===
async def convert_with_ffmpeg(input_path, output_path):
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, output_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return os.path.exists(output_path)
    except Exception:
        return False

# === Конвертация изображений ===
def convert_image(input_path, output_format):
    try:
        if output_format.lower() == 'svg':
            out_path = f"{input_path}.svg"
            shutil.copy(input_path, out_path)
            return out_path
        out_path = f"{input_path}.{output_format}"
        img = Image.open(input_path)
        img.save(out_path)
        return out_path
    except Exception:
        return None

# === Конвертация архивов ===
async def convert_archive(input_path, target_fmt):
    out_path = f"{input_path}.{target_fmt}"
    try:
        if target_fmt == 'zip':
            with pyzipper.AESZipFile(out_path, 'w') as zipf:
                if input_path.endswith('.rar'):
                    with rarfile.RarFile(input_path) as rf:
                        for f in rf.infolist():
                            zipf.writestr(f.filename, rf.read(f))
                else:
                    shutil.copy(input_path, out_path)
        elif target_fmt == 'rar':
            shutil.copy(input_path, out_path)
        return out_path if os.path.exists(out_path) else None
    except Exception as e:
        print(e)
        return None

# === Меню выбора типа ===
async def send_type_menu(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Конвертировать изображение", callback_data="type_image"))
    markup.add(InlineKeyboardButton("Конвертировать видео", callback_data="type_video"))
    markup.add(InlineKeyboardButton("Конвертировать аудио", callback_data="type_audio"))
    markup.add(InlineKeyboardButton("Конвертировать документ", callback_data="type_document"))
    markup.add(InlineKeyboardButton("Конвертировать архив", callback_data="type_archive"))
    await bot.send_message(chat_id, "📤 Выберите тип файла для конвертации:", reply_markup=markup)

# === Команды ===
@dp.message_handler(commands=['start', 'help'])
async def start(msg: types.Message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Конвертировать изображение", callback_data="type_image"))
    markup.add(InlineKeyboardButton("Конвертировать видео", callback_data="type_video"))
    markup.add(InlineKeyboardButton("Конвертировать аудио", callback_data="type_audio"))
    markup.add(InlineKeyboardButton("Конвертировать документ", callback_data="type_document"))
    markup.add(InlineKeyboardButton("Конвертировать архив", callback_data="type_archive"))
    await msg.reply("👋 Привет! Я бот-конвертер.\nВыбери, что хочешь конвертировать:", reply_markup=markup)

# === Скрытая команда /convert (работает и в личке, и в группе) ===
@dp.message_handler(commands=['convert'])
async def convert_command(msg: types.Message):
    await send_type_menu(msg.chat.id)

# === Выбор типа ===
@dp.callback_query_handler(lambda c: c.data.startswith("type_"))
async def choose_file_type(callback_query: types.CallbackQuery):
    ftype = callback_query.data.replace("type_", "")
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"📥 Отправьте файл для конвертации ({ftype})")
    user_file_store[callback_query.from_user.id] = {'expected_type': ftype}

# === Приём файла ===
@dp.message_handler(content_types=['document', 'photo', 'video', 'audio'])
async def receive_file(msg: types.Message):
    user_id = msg.from_user.id
    file_info = None
    file_name = "file"

    if msg.document:
        file_info = await bot.get_file(msg.document.file_id)
        file_name = msg.document.file_name
    elif msg.photo:
        file_info = await bot.get_file(msg.photo[-1].file_id)
        file_name = "photo.jpg"
    elif msg.video:
        file_info = await bot.get_file(msg.video.file_id)
        file_name = "video.mp4"
    elif msg.audio:
        file_info = await bot.get_file(msg.audio.file_id)
        file_name = msg.audio.file_name or "audio.mp3"
    else:
        await msg.reply("❌ Неверный формат файла")
        return

    ftype = detect_type(file_name)
    temp_path = tempfile.mktemp()
    await bot.download_file(file_info.file_path, temp_path)
    user_file_store[user_id] = {'path': temp_path, 'type': ftype}

    markup = InlineKeyboardMarkup(row_width=3)
    for fmt in FORMAT_OPTIONS.get(ftype, []):
        markup.add(InlineKeyboardButton(f"→ {fmt}", callback_data=f"convert_{fmt}"))

    await msg.reply("Выберите формат для конвертации:", reply_markup=markup)

# === Обработка конвертации ===
@dp.callback_query_handler(lambda c: c.data.startswith("convert_"))
async def convert_file_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    target_fmt = callback_query.data.replace("convert_", "")
    await bot.answer_callback_query(callback_query.id, "⏳ Конвертирую...")

    if user_id not in user_file_store or 'path' not in user_file_store[user_id]:
        await bot.send_message(user_id, "❌ Файл не найден. Отправь заново.")
        return

    temp_data = user_file_store[user_id]
    input_path = temp_data['path']
    ftype = temp_data['type']
    out_path = f"{input_path}.{target_fmt}"
    success = False

    if ftype == 'image':
        converted = convert_image(input_path, target_fmt)
        success = converted is not None
        if success:
            out_path = converted
    elif ftype == 'archive':
        converted = await convert_archive(input_path, target_fmt)
        success = converted is not None
        if success:
            out_path = converted
    else:
        success = await convert_with_ffmpeg(input_path, out_path)

    if success and os.path.exists(out_path):
        await bot.send_document(user_id, open(out_path, 'rb'))
        await bot.send_message(user_id, "✅ Конвертация завершена!")
    else:
        await bot.send_message(user_id, "❌ Ошибка при конвертации 😔")

    # Очистка временных файлов
    for p in [input_path, out_path]:
        try:
            if os.path.exists(p):
                os.remove(p)
        except:
            pass

    user_file_store.pop(user_id, None)

# === Запуск ===
if __name__ == "__main__":
    print("🚀 Бот запущен...")
    executor.start_polling(dp, skip_updates=True)
