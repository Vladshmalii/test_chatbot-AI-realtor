from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

def contact_keyboard() -> ReplyKeyboardMarkup:
    button = KeyboardButton(text="📞 Поділитись контактом", request_contact=True)
    keyboard = ReplyKeyboardMarkup(keyboard=[[button]], resize_keyboard=True, one_time_keyboard=True)
    return keyboard
