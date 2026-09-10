import os
import sqlite3
import threading
from flask import Flask
from telebot import TeleBot, types

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

bot = TeleBot(TOKEN)
app = Flask(__name__)

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
            price REAL,
            item_data TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.chat.id
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    conn.commit()
    
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
    balance = cur.fetchone()[0]
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛍️ تصفح المنتجات", callback_data="view_products"),
        types.InlineKeyboardButton("💳 شحن الرصيد", callback_data="deposit"),
        types.InlineKeyboardButton("👤 حسابي", callback_data="my_account"),
        types.InlineKeyboardButton("📞 الدعم الفني", callback_data="support")
    )
    bot.send_message(
        uid, 
        f"مرحباً بك في المتجر الرقمي!\n\n💰 رصيدك الحالي: **{balance}$**", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_clicks(call):
    uid = call.message.chat.id
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()

    if call.data == "view_products":
        cur.execute("SELECT DISTINCT name, price FROM products")
        items = cur.fetchall()
        
        if not items:
            bot.answer_callback_query(call.id, "لا توجد منتجات متوفرة حالياً!", show_alert=True)
            conn.close()
            return

        markup = types.InlineKeyboardMarkup()
        for name, price in items:
            cur.execute("SELECT COUNT(*) FROM products WHERE name = ?", (name,))
            count = cur.fetchone()[0]
            btn_text = f"{name} | {price}$ (المتبقي: {count})"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_{name}"))
            
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_home"))
        bot.edit_message_text("اختر المنتج للشراء:", uid, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("buy_"):
        product_name = call.data.split("buy_")[1]
        
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        balance = cur.fetchone()[0]
        
        cur.execute("SELECT id, price, item_data FROM products WHERE name = ? LIMIT 1", (product_name,))
        product = cur.fetchone()

        if not product:
            bot.answer_callback_query(call.id, "عذراً، نفدت الكمية من هذا المنتج!", show_alert=True)
        elif balance < product[1]:
            bot.answer_callback_query(call.id, f"رصيدك غير كافٍ! تحتاج {product[1]}$", show_alert=True)
        else:
            prod_id, price, item_data = product
            new_balance = balance - price
            cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, uid))
            cur.execute("DELETE FROM products WHERE id = ?", (prod_id,))
            conn.commit()

            bot.send_message(
                uid,
                f"✅ **تم الشراء بنجاح!**\n\n📦 **المنتج:** {product_name}\n🔑 **بيانات الاستلام:**\n`{item_data}`\n\n💰 **رصيدك المتبقي:** {new_balance}$",
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, "تم استلام طلبك بنجاح!")

    elif call.data == "my_account":
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        bal = cur.fetchone()[0]
        bot.answer_callback_query(call.id, f"معرفك (ID): {uid}\nرصيدك الحالي: {bal}$", show_alert=True)

    elif call.data == "deposit":
        bot.send_message(uid, "💳 لشحن رصيدك، يرجى مراسلة الدعم الفني وإرسال إشعار التحويل.")

    elif call.data == "support":
        bot.send_message(uid, "📞 للتواصل مع الدعم الفني: راسل المشرف مباشرة.")

    elif call.data == "back_home":
        start_cmd(call.message)

    conn.close()

@bot.message_handler(commands=['add'])
def add_product(message):
    if message.chat.id != ADMIN_ID:
        return

    try:
        parts = message.text.split(" ", 3)
        name = parts[1]
        price = float(parts[2])
        data = parts[3]

        conn = sqlite3.connect("shop.db")
        cur = conn.cursor()
        cur.execute("INSERT INTO products (name, price, item_data) VALUES (?, ?, ?)", (name, price, data))
        conn.commit()
        conn.close()

        bot.reply_to(message, f"✅ تمت إضافة قطعة جديدة إلى ({name}) بسعر {price}$.")
    except Exception:
        bot.reply_to(message, "⚠️ خطأ في الصيغة!\nالصيغة الصحيحة:\n`/add Netflix 5.0 user@mail.com:pass123`", parse_mode="Markdown")

@bot.message_handler(commands=['setbal'])
def set_balance(message):
    if message.chat.id != ADMIN_ID:
        return
    try:
        _, uid, amount = message.text.split()
        conn = sqlite3.connect("shop.db")
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amount), int(uid)))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ تم شحن {amount}$ للمستخدم {uid}.")
        bot.send_message(int(uid), f"🎉 **تمت إضافة رصيد جديد إلى حسابك:** +{amount}$", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "⚠️ خطأ في الصيغة!\nالصيغة الصحيحة:\n`/setbal 123456789 10`", parse_mode="Markdown")

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
  
