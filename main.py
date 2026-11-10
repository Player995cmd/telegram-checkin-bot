import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
import aiosqlite

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
CHANNEL_ID = "@your_channel_username"
CHANNEL_URL = "https://t.me/your_channel_username"
ADMIN_ID = 123456789

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_NAME = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                streak_count INTEGER DEFAULT 0,
                last_checkin TEXT
            )
        ''')
        await db.commit()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

def get_join_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 عضویت در کانال", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_join")]
    ])

def get_main_keyboard(user_id: int):
    buttons = [[KeyboardButton(text="📍 ثبت حضور امروز")]]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️ پنل مدیریت")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 تعداد کاربران"), KeyboardButton(text="📜 لیست حضور کاربران")],
        [KeyboardButton(text="📢 ارسال پیام همگانی (Broadcast)")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ], resize_keyboard=True)

async def check_channel_membership(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Error checking membership: {e}")
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
            (user_id, username)
        )
        await db.commit()

    is_member = await check_channel_membership(user_id)
    if not is_member:
        await message.answer(
            "⚠️ برای استفاده از ربات باید ابتدا عضو کانال ما شوید:",
            reply_markup=get_join_keyboard()
        )
        return

    await message.answer(
        "👋 سلام! به ربات ثبت حضور روزانه خوش آمدید.",
        reply_markup=get_main_keyboard(user_id)
    )

@dp.callback_query(F.data == "check_join")
async def callback_check_join(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_member = await check_channel_membership(user_id)
    
    if is_member:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "✅ عضویت شما تایید شد! به منوی اصلی خوش آمدید.",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        await callback.answer("❌ شما هنوز عضو کانال نشده‌اید!", show_alert=True)

@dp.message(F.text == "📍 ثبت حضور امروز")
async def process_daily_checkin(message: types.Message):
    user_id = message.from_user.id
    
    is_member = await check_channel_membership(user_id)
    if not is_member:
        await message.answer(
            "⚠️ شما از کانال لفت داده‌اید! لطفاً مجدداً عضو شوید تا حضور شما ثبت شود:",
            reply_markup=get_join_keyboard()
        )
        return

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT streak_count, last_checkin FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            
            streak_count = row[0] if row else 0
            last_checkin_str = row[1] if row else None
            
            if last_checkin_str:
                last_checkin_date = datetime.strptime(last_checkin_str, "%Y-%m-%d").date()
                if last_checkin_date == now.date():
                    await message.answer("❌ شما امروز حضور خود را ثبت کرده‌اید! فردا دوباره تلاش کنید.")
                    return
                elif last_checkin_date == now.date() - timedelta(days=1):
                    streak_count = min(streak_count + 1, 90)
                else:
                    streak_count = 1
            else:
                streak_count = 1

        await db.execute(
            "UPDATE users SET streak_count = ?, last_checkin = ? WHERE user_id = ?",
            (streak_count, today_str, user_id)
        )
        await db.commit()

    await message.answer(f"🎉 حضور امروز شما با موفقیت ثبت شد!\n🔥 شمارشگر حضور شما: {streak_count} از ۹۰ روز")

@dp.message(F.text == "⚙️ پنل مدیریت")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("به پنل مدیریت خوش آمدید:", reply_markup=get_admin_keyboard())

@dp.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_to_main(message: types.Message):
    await message.answer("منوی اصلی:", reply_markup=get_main_keyboard(message.from_user.id))

@dp.message(F.text == "📊 تعداد کاربران")
async def admin_user_count(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            count = (await cursor.fetchone())[0]
    await message.answer(f"👥 تعداد کل کاربران ربات: {count} نفر")

@dp.message(F.text == "📜 لیست حضور کاربران")
async def admin_user_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, username, streak_count, last_checkin FROM users ORDER BY streak_count DESC LIMIT 20") as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        await message.answer("هیچ کاربر یا ثبت حضوری یافت نشد.")
        return
        
    text = "📜 **لیست برترین روزهای حضور (۲۰ کاربر برتر):**\n\n"
    for row in rows:
        text += f"👤 @{row[1]} (ID: `{row[0]}`)\n🔥 روزهای حضور: {row[2]} | آخرین ثبت: {row[3]}\n-------------------\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📢 ارسال پیام همگانی (Broadcast)")
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("لطفاً پیامی که می‌خواهید به تمام کاربران ارسال شود را وارد/فوروارد کنید:")

@dp.message(BroadcastState.waiting_for_message)
async def admin_broadcast_process(message: types.Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()

    success, failed = 0, 0
    status_msg = await message.answer("⏳ در حال ارسال پیام همگانی...")
    
    for (user_id,) in users:
        try:
            await message.copy_to(chat_id=user_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(f"✅ ارسال همگانی پایان یافت.\n\n👍 ارسال موفق: {success}\n❌ ناموفق / بلاک شده: {failed}")

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
