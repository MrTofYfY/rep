import os
from pytube import YouTube
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# 🔑 ВСТАВЬ СЮДА СВОЙ ТОКЕН от BotFather
TELEGRAM_BOT_TOKEN = '8135489502:AAFmNNrLtp08hM4bkLIm4pRhs4cSFkggpfE'

# 📥 Скачивание видео или аудио
def download_youtube_media(url: str, format: str, output_path='downloads'):
    yt = YouTube(url)

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    if format == 'video':
        stream = yt.streams.filter(progressive=True, file_extension='mp4', res="360p").first()
        if not stream:
            raise Exception("Видео в 360p не найдено.")
        file_path = stream.download(output_path=output_path)
    elif format == 'audio':
        stream = yt.streams.filter(only_audio=True).first()
        if not stream:
            raise Exception("Аудио не найдено.")
        file_path = stream.download(output_path=output_path)
        base, _ = os.path.splitext(file_path)
        mp3_path = base + '.mp3'
        os.rename(file_path, mp3_path)
        file_path = mp3_path
    else:
        raise Exception("Неверный формат.")

    print(f"✅ Скачано: {file_path}")
    return file_path

# 🟢 Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Отправь мне ссылку на видео с YouTube.")

# 📩 При получении ссылки — предлагаем выбор формата
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("❗ Пожалуйста, отправь ссылку на YouTube.")
        return

    # Сохраняем ссылку в context
    context.user_data['youtube_url'] = url

    # Показываем кнопки
    keyboard = [
        [InlineKeyboardButton("📹 Видео (360p)", callback_data='video')],
        [InlineKeyboardButton("🎧 Аудио (MP3)", callback_data='audio')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Что ты хочешь скачать?", reply_markup=reply_markup)

# 🎯 Обработка нажатия кнопок
async def handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    format = query.data
    url = context.user_data.get('youtube_url')

    if not url:
        await query.edit_message_text("❗ Ссылка не найдена. Отправь её снова.")
        return

    await query.edit_message_text("⏬ Загружаю, подожди немного...")

    try:
        file_path = download_youtube_media(url, format)

        with open(file_path, 'rb') as f:
            if format == 'video':
                await query.message.reply_video(video=f)
            else:
                await query.message.reply_audio(audio=f)

        os.remove(file_path)
        print(f"🗑 Удалён файл: {file_path}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await query.message.reply_text(f"Ошибка: {e}")

# 🚀 Запуск бота
def main():
    print("🚀 Запуск Telegram-бота...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_format_choice))

    print("✅ Бот работает. Ожидаю сообщения...")
    app.run_polling()

if __name__ == 'main':
    main()