import asyncio
import os
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import (init_db, add_order, get_all_orders, get_order_details,
                      update_order_status, update_order_due_date, delete_order,
                      reset_database, get_orders_for_notification, mark_notification_sent)

logging.basicConfig(level=logging.INFO)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

class OrderState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_description = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_due_date = State()

private_chat_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить заказ")],
        [KeyboardButton(text="📋 Все заказы"), KeyboardButton(text="⚙️ Стадия заказа")],
        [KeyboardButton(text="⚠️ Сброс")]
    ],
    resize_keyboard=True
)

group_chat_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Все заказы")],
    ],
    resize_keyboard=True
)

async def set_main_menu(bot: Bot):
    await bot.set_my_commands([BotCommand(command='/start', description='Запуск / Перезапуск бота')])

@dp.message(Command("get_chat_id"))
async def get_chat_id(message: types.Message):
    await message.answer(f"ID этого чата: `{message.chat.id}`", parse_mode="MarkdownV2")

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить заказ")],
            [KeyboardButton(text="📋 Все заказы"), KeyboardButton(text="⚙️ Стадия заказа")]
        ],
        resize_keyboard=True
    )
    # Показываем админскую клавиатуру только админу в личке
    if str(message.from_user.id) == ADMIN_ID and message.chat.type == 'private':
        await message.answer(
            "Здравствуйте, Администратор! Вам доступны все функции, включая сброс.",
            reply_markup=private_chat_kb
        )
    # Обычному пользователю в личке
    elif message.chat.type == 'private':
        await message.answer(
            "Здравствуйте! Здесь вы можете добавить новый заказ.",
            reply_markup=user_kb
        )
    # В группе
    else:
        await message.answer(
            "Бот для заказов активен. Используйте кнопку ниже для просмотра заказов.",
            reply_markup=group_chat_kb
        )

@dp.message(F.text == "➕ Добавить заказ")
async def start_order_process(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await message.answer("Добавлять заказы можно только в личном чате с ботом.")
        return
    await state.update_data(chat_id=message.chat.id)
    await message.answer("Загрузите фотографию для заказа.", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(OrderState.waiting_for_photo)

@dp.message(OrderState.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("Фото принято. Теперь введите описание заказа.")
    await state.set_state(OrderState.waiting_for_description)

@dp.message(OrderState.waiting_for_description, F.text)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Описание принято. Теперь введите номер телефона клиента.")
    await state.set_state(OrderState.waiting_for_phone)

@dp.message(OrderState.waiting_for_phone, F.text)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Телефон принят. Теперь введите адрес доставки.")
    await state.set_state(OrderState.waiting_for_address)

@dp.message(OrderState.waiting_for_address, F.text)
async def process_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("Адрес принят. Укажите крайний срок сдачи в формате ДД.ММ.ГГГГ")
    await state.set_state(OrderState.waiting_for_due_date)

@dp.message(OrderState.waiting_for_due_date, F.text)
async def process_due_date(message: types.Message, state: FSMContext):
    try:
        due_date = datetime.strptime(message.text, "%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты. Пожалуйста, введите в формате ДД.ММ.ГГГГ")
        return
    await state.update_data(due_date=due_date.isoformat())
    user_data = await state.get_data()
    await add_order(user_data)
    
    kb = private_chat_kb if str(message.from_user.id) == ADMIN_ID else ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ Добавить заказ")],[KeyboardButton(text="📋 Все заказы"), KeyboardButton(text="⚙️ Стадия заказа")]],resize_keyboard=True)
    await message.answer("✅ Заказ успешно создан!", reply_markup=kb)

    if GROUP_ID:
        try:
            await bot.send_message(chat_id=GROUP_ID,text=f"✅ <b>Добавлен новый заказ!</b>\n\nВоспользуйтесь кнопкой «Все заказы», чтобы посмотреть детали.")
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление в группу {GROUP_ID}: {e}")
    await state.clear()

@dp.message(F.text == "📋 Все заказы")
async def show_all_orders(message: types.Message):
    orders = await get_all_orders()
    if not orders:
        await message.answer("Активных заказов пока нет.")
        return
    builder = InlineKeyboardBuilder()
    for order_id, description in orders:
        builder.add(InlineKeyboardButton(text=f"Заказ №{order_id} - {description[:20]}...", callback_data=f"view_order:{order_id}"))
    builder.adjust(1)
    await message.answer("Выберите заказ для просмотра деталей:", reply_markup=builder.as_markup())

@dp.message(F.text == "⚙️ Стадия заказа")
async def change_status_menu(message: types.Message):
    if message.chat.type != 'private':
        await message.answer("Управлять стадиями заказов можно только в личном чате с ботом.")
        return
    orders = await get_all_orders()
    if not orders:
        await message.answer("Активных заказов пока нет.")
        return
    builder = InlineKeyboardBuilder()
    for order_id, description in orders:
        builder.add(InlineKeyboardButton(text=f"Заказ №{order_id} - {description[:20]}...", callback_data=f"edit_order:{order_id}"))
    builder.adjust(1)
    await message.answer("Выберите заказ для изменения или удаления:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("view_order:"))
async def view_order_callback(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    order_details = await get_order_details(order_id)
    chat_id_to_send = callback.message.chat.id
    if order_details:
        _, _, photo_id, desc, phone, address, status, _, due_date_iso, _ = order_details
        due_date_str = datetime.fromisoformat(due_date_iso).strftime("%d.%m.%Y")
        caption = (f"<b>Детали Заказа №{order_id}</b>\n\n<b>Описание:</b> {desc}\n<b>Статус:</b> {status}\n<b>Срок сдачи:</b> {due_date_str}\n<b>Телефон:</b> {phone}\n<b>Адрес:</b> {address}")
        await bot.send_photo(chat_id=chat_id_to_send, photo=photo_id, caption=caption)
        await callback.message.delete()
    else:
        await bot.send_message(chat_id_to_send, "Не удалось найти информацию о заказе.")
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_order:"))
async def show_edit_menu(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    builder = InlineKeyboardBuilder()
    statuses = ["В работе", "Готов", "Завершён"]
    for status in statuses:
        builder.add(InlineKeyboardButton(text=status, callback_data=f"set_status:{order_id}:{status}"))
    days = [3, 7, 10, 15]
    for day in days:
        builder.add(InlineKeyboardButton(text=f"{day} дней", callback_data=f"set_due:{order_id}:{day}"))
    builder.add(InlineKeyboardButton(text="❌ Удалить заказ", callback_data=f"delete_confirm:{order_id}"))
    builder.adjust(3, 2, 1)
    await callback.message.edit_text(f"Изменение заказа №{order_id}:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set_status:"))
async def set_status_callback(callback: types.CallbackQuery):
    _, order_id, new_status = callback.data.split(":")
    await update_order_status(int(order_id), new_status)
    await callback.message.edit_text(f"✅ Статус заказа №{order_id} изменен на '{new_status}'.")
    await callback.answer()

@dp.callback_query(F.data.startswith("set_due:"))
async def set_due_callback(callback: types.CallbackQuery):
    _, order_id, days = callback.data.split(":")
    new_due_date = datetime.now() + timedelta(days=int(days))
    await update_order_due_date(int(order_id), new_due_date.isoformat())
    await callback.message.edit_text(f"✅ Срок для заказа №{order_id} установлен на {new_due_date.strftime('%d.%m.%Y')}.")
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_confirm:"))
async def delete_confirm_callback(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_execute:{order_id}"))
    builder.add(InlineKeyboardButton(text="◀️ Нет, назад", callback_data=f"edit_order:{order_id}"))
    await callback.message.edit_text(f"Вы уверены, что хотите удалить заказ №{order_id}?", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("delete_execute:"))
async def delete_execute_callback(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    await delete_order(order_id)
    await callback.message.edit_text(f"🗑️ Заказ №{order_id} был успешно удален.")
    if GROUP_ID:
        try:
            await bot.send_message(GROUP_ID, f"🗑️ Заказ №{order_id} был удален.")
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление об удалении в группу {GROUP_ID}: {e}")
    await callback.answer()

@dp.message(F.text == "⚠️ Сброс")
async def reset_handler(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💣 Да, удалить всё!", callback_data="reset_execute_confirm"))
    builder.add(InlineKeyboardButton(text="Отмена", callback_data="reset_cancel"))
    await message.answer(
        "Вы уверены, что хотите **ПОЛНОСТЬЮ УДАЛИТЬ ВСЕ ЗАКАЗЫ** и сбросить счетчик ID?\n\n"
        "Это действие необратимо!",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "reset_cancel")
async def reset_cancel_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Сброс отменен.")

@dp.callback_query(F.data == "reset_execute_confirm")
async def reset_execute_confirm_callback(callback: types.CallbackQuery):
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.answer("У вас нет прав!", show_alert=True)
        return
    await reset_database()
    await callback.message.edit_text("✅ База данных полностью очищена. Счетчик заказов сброшен на 1.")
    if GROUP_ID:
        try:
            # ИСПРАВЛЕННАЯ СТРОКА
            await bot.send_message(GROUP_ID, "⚠️ Администратор произвёл сброс базы данных.")
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление о сбросе в группу {GROUP_ID}: {e}")
    await callback.answer()

async def check_deadlines():
    orders = await get_orders_for_notification()
    now = datetime.now()
    for order in orders:
        order_id, chat_id, description, due_date_iso = order
        if not chat_id: continue
        due_date = datetime.fromisoformat(due_date_iso)
        if due_date > now and (due_date - now) < timedelta(days=1):
            try:
                await bot.send_message(chat_id=chat_id,text=f"❗️<b>УВЕДОМЛЕНИЕ</b>❗️\n\nСрок сдачи заказа №{order_id} ({description}) истекает завтра, {due_date.strftime('%d.%m.%Y')}!")
                await mark_notification_sent(order_id)
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление для заказа {order_id} в чат {chat_id}: {e}")

async def main():
    await init_db()
    await set_main_menu(bot)
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(check_deadlines, 'interval', hours=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())