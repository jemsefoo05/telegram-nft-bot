import os
import sqlite3
import threading
from flask import Flask
from telebot import TeleBot, types

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
# ضع رقم معرف باينانس الخاص بك هنا لاستقبال التحويلات
BINANCE_PAY_ID = os.environ.get("BINANCE_PAY_ID", "1004897974")

bot = TeleBot(TOKEN)
app = Flask(__name__)

# حالات المستخدمين للتعامل مع الرسائل المتتالية
USER_STATES = {}

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price REAL,
            item_data TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- خادم Render لضمان بقاء البوت حياً ---
@app.route('/')
def home():
    return "Store Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# زر القائمة الدائم بالأسفل
def persistent_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🎮 فتح المتجر (Menu)"))
    return markup

# --- القائمة الرئيسية للمتجر ---
def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 المنتجات", callback_data="products_list"),
        types.InlineKeyboardButton("💰 محفظتي", callback_data="my_wallet")
    )
    markup.add(
        types.InlineKeyboardButton("📦 سجل طلباتي", callback_data="orders_history"),
        types.InlineKeyboardButton("🤝 دعوة الأصدقاء (USDT)", callback_data="referral")
    )
    markup.add(
        types.InlineKeyboardButton("🎟️ استخدام كوبون", callback_data="coupon"),
        types.InlineKeyboardButton("🎧 الدعم الفني", callback_data="support")
    )
    return markup

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    uid = message.chat.id
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    conn.commit()
    conn.close()

    text = "🛒 **مرحباً بك في متجر الخدمات الرقمية!**\nالمنصة الأسرع والأكثر أماناً لشراء وتفعيل الحسابات.\n\n👇 **اختر من القائمة بالأسفل:**"
    bot.send_message(uid, text, reply_markup=persistent_menu(), parse_mode="Markdown")
    bot.send_message(uid, "لوحة التحكم الرئيسية:", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text == "🎮 فتح المتجر (Menu)")
def open_menu_btn(message):
    send_welcome(message)

# --- معالجة الأزرار التفاعلية ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.message.chat.id
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()

    if call.data == "home":
        USER_STATES.pop(uid, None)
        text = "🛒 **مرحباً بك في المتجر!**\n\n👇 **اختر من القائمة بالأسفل:**"
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=get_main_menu(), parse_mode="Markdown")

    elif call.data == "my_wallet":
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        res = cur.fetchone()
        bal = res[0] if res else 0.0

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("➕ شحن الرصيد", callback_data="deposit_start"),
            types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")
        )
        text = f"💰 **محفظتك**\n\nالرصيد الحالي: **{bal:.2f} USDT**"
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "deposit_start":
        USER_STATES[uid] = "WAITING_DEPOSIT_AMOUNT"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="home"))
        bot.edit_message_text("💰 **شحن المحفظة**\n\nأدخل المبلغ الذي تريد إيداعه بوحدة USDT:\n\n*مثال: 5 أو 10.5*", uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "products_list":
        cur.execute("SELECT DISTINCT name, price FROM products")
        items = cur.fetchall()

        if not items:
            bot.answer_callback_query(call.id, "لا توجد منتجات متوفرة حالياً.", show_alert=True)
            conn.close()
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for name, price in items:
            markup.add(types.InlineKeyboardButton(f"{name} — {price} USDT", callback_data=f"show_{name}"))
        markup.add(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home"))
        bot.edit_message_text("اختر المنتج لعرض التفاصيل:", uid, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("show_"):
        prod_name = call.data.split("show_")[1]
        cur.execute("SELECT description, price FROM products WHERE name = ? LIMIT 1", (prod_name,))
        row = cur.fetchone()
        
        cur.execute("SELECT COUNT(*) FROM products WHERE name = ?", (prod_name,))
        stock = cur.fetchone()[0]

        if row:
            desc, price = row
            text = (
                f"📦 **{prod_name}**\n\n"
                f"{desc}\n\n"
                f"💵 **السعر:** {price} USDT\n"
                f"📊 **المتوفر:** {stock} قطعة\n"
                f"_____________________"
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("🛒 شراء الآن", callback_data=f"buy_options_{prod_name}"),
                types.InlineKeyboardButton("🔙 الرجوع للقائمة", callback_data="products_list")
            )
            bot.edit_message_text(text, uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("buy_options_"):
        prod_name = call.data.split("buy_options_")[1]
        cur.execute("SELECT price FROM products WHERE name = ? LIMIT 1", (prod_name,))
        row = cur.fetchone()

        if not row:
            bot.answer_callback_query(call.id, "نفدت الكمية!", show_alert=True)
            conn.close()
            return

        price = row[0]
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💰 الدفع من الرصيد", callback_data=f"confirm_pay_{prod_name}"),
            types.InlineKeyboardButton("💳 باستخدام باينانس (إيداع أولاً)", callback_data="deposit_start"),
            types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")
        )
        text = f"💳 **اختر طريقة الدفع**\n\nالمنتج: **{prod_name}**\nالإجمالي: **{price} USDT**"
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("confirm_pay_"):
        prod_name = call.data.split("confirm_pay_")[1]
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        bal = cur.fetchone()[0]

        cur.execute("SELECT id, price, item_data FROM products WHERE name = ? LIMIT 1", (prod_name,))
        item = cur.fetchone()

        if not item:
            bot.answer_callback_query(call.id, "عذراً نفد المخزون!", show_alert=True)
        elif bal < item[1]:
            bot.answer_callback_query(call.id, f"رصيدك غير كافٍ! تحتاج {item[1]} USDT", show_alert=True)
        else:
            item_id, price, item_data = item
            new_bal = bal - price
            cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_bal, uid))
            cur.execute("DELETE FROM products WHERE id = ?", (item_id,))
            conn.commit()

            bot.send_message(
                uid,
                f"✅ **تم الشراء بنجاح!**\n\n"
                f"📦 **المنتج:** {prod_name}\n"
                f"🔑 **بيانات الاستلام:**\n`{item_data}`\n\n"
                f"💰 **رصيدك الحالي:** {new_bal:.2f} USDT",
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, "تم استلام الطلب بنجاح!")

    elif call.data == "support":
        bot.send_message(uid, "🎧 للدعم الفني والاستفسار، يرجى مراسلة الإدارة مباشرة.")

    elif call.data.startswith("approve_"):
        # تأكيد شحن الرصيد من قبل الأدمن
        _, target_uid, amt = call.data.split("_")
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), int(target_uid)))
        conn.commit()
        bot.send_message(int(target_uid), f"🎉 **تم تأكيد عملية الإيداع بنجاح!**\nتمت إضافة **+{amt} USDT** إلى محفظتك.", parse_mode="Markdown")
        bot.edit_message_text(f"✅ تم شحن {amt} USDT للمستخدم {target_uid}", uid, call.message.message_id)

    conn.close()

# --- معالجة الرسائل النصية المدخلة من المستخدم ---
@bot.message_handler(func=lambda msg: msg.chat.id in USER_STATES)
def handle_user_inputs(message):
    uid = message.chat.id
    state = USER_STATES.get(uid)

    if state == "WAITING_DEPOSIT_AMOUNT":
        try:
            amount = float(message.text)
            USER_STATES[uid] = f"AWAITING_ORDER_ID_{amount}"

            text = (
                f"🟡 **شحن المحفظة عبر Binance Pay**\n\n"
                f"💰 المبلغ المطلوب: **{amount} USDT**\n"
                f"⏰ لديك 15 دقيقة لإتمام الدفع.\n"
                f"_____________________\n\n"
                f"قم بتحويل المبلغ بالضبط إلى حسابنا في باينانس:\n"
                f"🔹 رقم الحساب (Pay ID): `{BINANCE_PAY_ID}`\n"
                f"💰 المبلغ المطلوب: **{amount} USDT**\n\n"
                f"✅ **بعد إتمام التحويل، أرسل الآن رقم الطلب (Order ID) الخاص بالتحويل هنا مباشرة:**"
            )
            bot.send_message(uid, text, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "⚠️ يرجى إدخال رقم صحيح (مثال: 5 أو 10).")

    elif state.startswith("AWAITING_ORDER_ID_"):
        amount = state.split("AWAITING_ORDER_ID_")[1]
        order_id = message.text.strip()
        USER_STATES.pop(uid, None)

        bot.send_message(
            uid,
            f"⏳ **تم استلام رقم الطلب:** `{order_id}`\nيجري التحقق من العملية وتحديث رصيدك خلال دقائق.",
            parse_mode="Markdown"
        )

        # إرسال إشعار فوري للأدمن مع زر للموافقة السريعة
        if ADMIN_ID != 0:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ تأكيد الشحن للمستخدم", callback_data=f"approve_{uid}_{amount}")
            )
            admin_msg = (
                f"🔔 **طلب إيداع جديد!**\n\n"
                f"👤 المستخدم: `{uid}`\n"
                f"💵 المبلغ: **{amount} USDT**\n"
                f"🧾 رقم الطلب (Order ID): `{order_id}`"
            )
            bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup, parse_mode="Markdown")

# --- أوامر الأدمن الميسرة (إضافة وحذف وشحن) ---

@bot.message_handler(commands=['add'])
def add_product(message):
    """
    صيغة الإضافة المريحة باستخدام الفاصلة | لتتمكن من كتابة أسماء وأوصاف طويلة:
    /add اسم المنتج | وصف المنتج | السعر | الكود أو بيانات الحساب
    """
    if message.chat.id != ADMIN_ID:
        return

    try:
        parts = message.text.replace("/add ", "").split("|")
        name = parts[0].strip()
        desc = parts[1].strip()
        price = float(parts[2].strip())
        data = parts[3].strip()

        conn = sqlite3.connect("shop.db")
        cur = conn.cursor()
        cur.execute("INSERT INTO products (name, description, price, item_data) VALUES (?, ?, ?, ?)", (name, desc, price, data))
        conn.commit()
        conn.close()

        bot.reply_to(message, f"✅ **تمت إضافة المنتج بنجاح:**\n📦 {name}\n💵 {price} USDT")
    except Exception:
        bot.reply_to(
            message,
            "⚠️ **خطأ في التنسيق!** استخدم الفاصل العمودي `|` بالشكل التالي:\n\n"
            "`/add Adobe Express 12M | اشتراك سنوي يعمل برابط رسمي | 1.9 | https://redeem.adobe.com/xxxx`",
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['setbal'])
def set_balance_manual(message):
    """شحن رصيد يدوي: /setbal [user_id] [amount]"""
    if message.chat.id != ADMIN_ID:
        return
    try:
        _, uid, amount = message.text.split()
        conn = sqlite3.connect("shop.db")
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amount), int(uid)))
        conn.commit()
        conn.close()

        bot.reply_to(message, f"✅ تم شحن {amount} USDT للمعرف {uid}")
        bot.send_message(int(uid), f"🎉 تم شحن رصيدك بمبلغ: **{amount} USDT**", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "الصيغة: `/setbal 123456789 10`")

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
