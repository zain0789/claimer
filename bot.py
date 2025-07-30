# bot.py (الآمن - بدون توكنات)
import telebot
from database import db, User, GiftCode
from server import app
from datetime import datetime, timedelta
import uuid
import re
import io # <-- إضافة مكتبة io لمعالجة الملفات
import os # <-- إضافة os للوصول لمتغيرات البيئة

# - استخدم متغير بيئة علشان التوكن -
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN مش محدد. لازم تحدد التوكن في متغير البيئة 'BOT_TOKEN'.")

bot = telebot.TeleBot(BOT_TOKEN)

# - إضافة متغير لتتبع حالة المستخدم -
user_states = {} # {user_id: "state"}

# ضع معرفك الرقمي على تليغرام هنا (بدون @) علشان تقدر تستخدم /create_gift
# مثال: SUPPORT_USER_IDS = ['123456789']
SUPPORT_USER_ID = os.environ.get('SUPPORT_USER_ID') or '7664032817' # <-- استخدم متغير بيئة
SUPPORT_USER_IDS = [SUPPORT_USER_ID]

# -
# ربط قاعدة البيانات
with app.app_context():
    db.create_all()

def generate_script_token():
    """إنشاء رمز فرد للسكربت"""
    return "scr_" + uuid.uuid4().hex[:16]

def is_user_subscribed(user_id):
    """التحقق من صلاحية الاشتراك"""
    with app.app_context():
        user = User.query.filter_by(user_id=str(user_id), is_active=True).first()
        if user and user.subscription_end and user.subscription_end > datetime.utcnow():
            return True
    return False

def main_menu_keyboard():
    """لوحة المفاتيح الرئيسية"""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📱 تحميل السكربت', '🎟️ استبدال كود')
    markup.row('👤 حسابي', '❓ المساعدة')
    markup.row('👤 تسجيل الاسم') # إضافة زر تسجيل الاسم
    return markup

# - إضافة أوامر ومعالجات لتسجيل اسم المستخدم -
@bot.message_handler(func=lambda message: message.text == '👤 تسجيل الاسم')
def start_username_registration(message):
    """بدء تسجيل اسم المستخدم"""
    user_id = str(message.from_user.id)
    # تسجيل حالة المستخدم
    user_states[user_id] = "awaiting_username"
    msg = bot.reply_to(message, "🪪 من فضلك، أدخل اسم المستخدم الذي ترغب به (مثلاً: john_doe):")
    bot.register_next_step_handler(msg, process_username_input)

def process_username_input(message):
    """معالجة اسم المستخدم المدخل"""
    user_id = str(message.from_user.id)
    # التحقق من الحالة
    if user_states.get(user_id) != "awaiting_username":
        bot.reply_to(message, "يرجى استخدام القائمة للتحكم في البوت.", reply_markup=main_menu_keyboard())
        if user_id in user_states:
            del user_states[user_id] # تنظيف الحالة
        return

    # الحصول على اسم المستخدم المدخل
    entered_username = message.text.strip()

    # التحقق من صحة الاسم
    if not entered_username or re.search(r'[^a-zA-Z0-9_]', entered_username) or len(entered_username) < 3 or len(entered_username) > 20:
        msg = bot.reply_to(message, "❌ الاسم غير صالح. يرجى إدخال اسم مستخدم يحتوي فقط على أحرف إنجليزية وأرقام وشرطات سفلية (_) وطوله بين 3 و 20 حرف:")
        bot.register_next_step_handler(msg, process_username_input)
        return # خروج من الدالة علشان يعيد المحاولة

    # التحقق من أن الاسم مش مستخدم من قبل
    with app.app_context():
        existing_user = User.query.filter_by(username=entered_username).first()
        if existing_user and existing_user.user_id != user_id: # السماح للمستخدم نفسه بتحديث اسمه
            msg = bot.reply_to(message, "❌ هذا الاسم مستخدم من قبل مستخدم آخر. من فضلك اختر اسماً مختلفاً:")
            bot.register_next_step_handler(msg, process_username_input)
            return # خروج من الدالة علشان يعيد المحاولة

        # إذا الاسم تمام
        # حذف حالة المستخدم
        if user_id in user_states:
            del user_states[user_id]

        # حفظ اسم المستخدم في قاعدة البيانات (أو تحديث اسم المستخدم الحالي)
        tg_username = message.from_user.username or "غير متوفر"
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            # إذا المستخدم مش مسجل أصلاً، نسجله بدون اشتراك وبدون إنشاء script_token
            # script_token رح ننشئه بس لما الاشتراك يتفعل
            user = User(
                user_id=user_id,
                username=entered_username, # اسم مخصص
                # telegram_username=tg_username,
                subscription_end=datetime.utcnow(), # اشتراك منتهي ابتدائياً
                script_token="", # مش هننشئ الرمز دلوقتي
                balance=0.0, # رصيد ابتدائي صفر
                is_active=False # مش مفعل اشتراك
            )
            db.session.add(user)
            db.session.commit()
            # رسالة بدون الرمز
            success_text = f"""✅ تم تسجيل اسم المستخدم الخاص بك بنجاح: `{entered_username}`
🔐 *ملاحظة:* رمز السكربت رح يتشال لك بعدين لما تفعل الاشتراك.
🎁 الآن، تحتاج إلى "كود هدية" لتفعيل اشتراكك.
- اطلب الكود من الدعم.
- بعد استلامه، استخدم الأمر `/redeem` أو اضغط على زر "🎟️ استبدال كود"."""
        else:
            # إذا المستخدم مسجل، نحدث اسمه المخصص
            old_username = user.username
            user.username = entered_username
            db.session.commit()
            if old_username and old_username != "غير متوفر":
                success_text = f"""✅ تم تحديث اسم المستخدم الخاص بك من `{old_username}` إلى: `{entered_username}`
🔐 *ملاحظة:* رمز السكربت رح يتشال لك بعدين لما تفعل الاشتراك (إذا ما عندكش واحد فعال).
🎁 الآن، تحتاج إلى "كود هدية" لتفعيل اشتراكك.
- اطلب الكود من الدعم.
- بعد استلامه، استخدم الأمر `/redeem` أو اضغط على زر "🎟️ استبدال كود"."""
            else:
                success_text = f"""✅ تم تسجيل اسم المستخدم الخاص بك بنجاح: `{entered_username}`
🔐 *ملاحظة:* رمز السكربت رح يتشال لك بعدين لما تفعل الاشتراك.
🎁 الآن، تحتاج إلى "كود هدية" لتفعيل اشتراكك.
- اطلب الكود من الدعم.
- بعد استلامه، استخدم الأمر `/redeem` أو اضغط على زر "🎟️ استبدال كود"."""

        bot.reply_to(message, success_text, parse_mode='Markdown', reply_markup=main_menu_keyboard())

# -

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """رسالة الترحيب والمساعدة"""
    welcome_text = """👋 مرحباً بك في بوت Stake Code Claimer!
🎁 للبدء، من فضلك قم بتسجيل اسم مستخدم مخصص لك.
بعد ذلك، ستحتاج إلى طلب "كود هدية" من الدعم لتفعيل اشتراكك.
اضغط على زر "👤 تسجيل الاسم" لبدء التسجيل."""
    # عرض القائمة الكاملة من أول البداية
    bot.reply_to(message, welcome_text, reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda message: message.text == '❓ المساعدة')
def send_help(message):
    """إرسال رسالة المساعدة"""
    help_text = """🤖 *بوت Stake Code Claimer - المساعدة*

📌 *كيفية الاستخدام:*
1. تسجيل اسم مستخدم مخصص لك.
2. الحصول على "كود هدية" من الدعم.
3. تفعيل الاشتراك باستخدام الكود.
4. تحميل السكربت وتشغيله على موقع Stake.com.

🔗 *الأوامر المتاحة:*
- /start - بدء البوت
- /help - عرض هذه المساعدة
- /status - عرض معلومات الحساب
- /script - تحميل السكربت
- /redeem <كود> - استبدال كود هدية (للدعم)

👤 *للمستخدمين المميزين (الدعم):*
- /create_gift <قيمة> - إنشاء كود هدية جديد

⚠️ *ملاحظات مهمة:*
- يجب تفعيل الاشتراك لتحميل واستخدام السكربت.
- لا تشارك رمز السكربت مع أحد.
- السكربت يعمل فقط على متصفح Chrome مع اضافة Tampermonkey."""
    bot.reply_to(message, help_text, parse_mode='Markdown', reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda message: message.text == '🎟️ استبدال كود')
def prompt_redeem_code(message):
    """مطالبة المستخدم بإدخال الكود"""
    msg = bot.reply_to(message, "🎫 من فضلك، أدخل كود الهدية الذي حصلت عليه:")
    bot.register_next_step_handler(msg, process_redeem_code)

@bot.message_handler(commands=['redeem'])
def prompt_redeem_code_command(message):
    """مطالبة المستخدم بإدخال الكود عبر الأمر"""
    msg = bot.reply_to(message, "🎫 من فضلك، أدخل كود الهدية الذي حصلت عليه:\nالتنسيق: `/redeem <الكود>`")
    bot.register_next_step_handler(msg, process_redeem_code)

def process_redeem_code(message):
    """معالجة كود الهدية المدخل"""
    try:
        user_id = str(message.from_user.id)
        # الحصول على الكود المدخل
        if message.text.startswith('/redeem'):
            command_parts = message.text.split()
            if len(command_parts) < 2:
                bot.reply_to(message, "❌ استخدام الأمر: `/redeem <كود_الهدية>`", parse_mode='Markdown', reply_markup=main_menu_keyboard())
                return
            code = command_parts[1].strip()
        else:
            code = message.text.strip()

        if not code:
            bot.reply_to(message, "❌ يرجى إدخال كود هدية صحيح.", reply_markup=main_menu_keyboard())
            return

        with app.app_context():
            # التحقق من صحة الكود
            gift_code = GiftCode.query.filter_by(code=code, is_used=False).first()
            if not gift_code:
                bot.reply_to(message, "❌ الكود غير صحيح أو مستخدم من قبل.", reply_markup=main_menu_keyboard())
                return

            # التحقق من المستخدم
            user = User.query.filter_by(user_id=user_id).first()
            if not user:
                bot.reply_to(message, "❌ يجب تسجيل اسم مستخدم أولاً. استخدم زر '👤 تسجيل الاسم'.", reply_markup=main_menu_keyboard())
                return

            # حساب مدة الاشتراك الجديدة
            days_to_add = int(gift_code.value_usd / 10) * 30 # كل 10$ = 30 يوم
            if days_to_add == 0:
                days_to_add = 30 # حد أدنى 30 يوم

            # تحديث تاريخ انتهاء الاشتراك
            if user.subscription_end and user.subscription_end > datetime.utcnow():
                # إذا الاشتراك ساري، نضيف على التاريخ الحالي
                new_end_date = user.subscription_end + timedelta(days=days_to_add)
            else:
                # إذا الاشتراك مش ساري أو منتهي، نبدأ من الآن
                new_end_date = datetime.utcnow() + timedelta(days=days_to_add)

            # تفعيل الاشتراك
            user.subscription_end = new_end_date
            user.is_active = True # تفعيل الاشتراك
            user.balance += gift_code.value_usd # إضافة قيمة الكود لرصيده

            # - إنشاء أو تحديث script_token بس لما الاشتراك يتفعل -
            if not user.script_token:
                user.script_token = generate_script_token()
            # -

            # تحديث بيانات الكود
            gift_code.is_used = True
            gift_code.used_by_user_id = user_id
            gift_code.used_at = datetime.utcnow()

            db.session.commit()

            success_text = f"""✅ تم تفعيل رمز الهدية بنجاح!
🎁 القيمة: {gift_code.value_usd} USD
⏳ مدة الاشتراك المضافة: {days_to_add} يوم
📅 اشتراكك الآن ساري حتى: {new_end_date.strftime('%Y-%m-%d %H:%M')}
💰 رصيدك الحالي: {user.balance:.2f} USD

🎉 مبروك! اشتراكك الآن مفعل ويمكنك تحميل السكربت."""

            bot.reply_to(message, success_text, reply_markup=main_menu_keyboard())

    except Exception as e:
        print(f"Error redeeming gift code: {e}")
        bot.reply_to(message, "❌ حدث خطأ أثناء معالجة الكود. يرجى المحاولة لاحقاً.", reply_markup=main_menu_keyboard())

@bot.message_handler(commands=['create_gift'])
def create_gift_code(message):
    """إنشاء كود هدية جديد (للدعم فقط)"""
    user_id = str(message.from_user.id)
    if user_id not in SUPPORT_USER_IDS:
        bot.reply_to(message, "❌ ليس لديك صلاحية استخدام هذا الأمر.")
        return

    try:
        # تنسيق الرسالة المتوقعة: /create_gift <قيمة_بالدولار>
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, "❌ استخدام الأمر: `/create_gift <قيمة_بالدولار>`\nمثال: `/create_gift 10`", parse_mode='Markdown')
            return

        value = float(command_parts[1])

        # إنشاء كود عشوائي
        import random, string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16)) # زيادة طول الكود لزيادة الأمان

        with app.app_context():
            new_gift_code = GiftCode(
                code=code,
                value_usd=value,
                issued_by=user_id
            )
            db.session.add(new_gift_code)
            db.session.commit()

            success_msg = f"""✅ تم إنشاء كود هدية جديد!
🎟️ الكود: `{code}`
💰 القيمة: {value} USD"""
            # إرسال الكود بشكل خاص للمستخدم المعني لاحقاً أو نخليه ينسخه من الرسالة
            bot.reply_to(message, success_msg, parse_mode='Markdown')

    except ValueError:
        bot.reply_to(message, "❌ القيمة يجب أن تكون رقماً. مثال: `/create_gift 10`", parse_mode='Markdown')
    except Exception as e:
        print(f"Error creating gift code: {e}")
        bot.reply_to(message, "❌ حدث خطأ أثناء إنشاء الكود.")

# - تعديل دالة تحميل السكربت علشان تتحقق من الاشتراك وبعت السكربت كملف مرفق -
@bot.message_handler(func=lambda message: message.text == '📱 تحميل السكربت')
@bot.message_handler(commands=['script'])
def handle_get_script(message):
    """إرسال السكربت المخصص للمستخدم بعد التحقق من الاشتراك فقط."""
    try:
        user_id = message.from_user.id
        # - التحقق من الاشتراك -
        # استخدم الدالة الموجودة علشان نكون موحدين في المنطق
        if not is_user_subscribed(user_id):
            # إذا الاشتراك مش مفعل أو انتهت صلاحيته
            subscribe_text = """❌ يجب تفعيل اشتراكك أولاً لاستخدام هذه الخدمة.
لتفعيل الاشتراك:
1. اطلب "كود هدية" من الدعم.
2. استخدم زر "🎟️ استبدال كود" في القائمة لإدخال الكود.
بعد التفعيل، رح تقدر تحصل على السكربت."""
            bot.reply_to(message, subscribe_text, reply_markup=main_menu_keyboard())
            return
        # -

        # - إذا الاشتراك مفعل، نكمل -
        with app.app_context():
            user = User.query.filter_by(user_id=str(user_id)).first()
            if user:
                # رسالة شرح التثبيت
                script_info = f"""🎯 السكربت الخاص بك جاهز!

📝 طريقة التثبيت:
1. ثبت اضافة Tampermonkey في متصفحك.
2. افتح الملف المرفق (`stake_claimer_{user.username}.user.js`).
3. Tampermonkey رح يكتشف السكربت تلقائيًا ويسألك عن التثبيت.
4. اضغط "تثبيت" أو "Install".

🔒 رمز السكربت الخاص بك: `{user.script_token}`
👤 اسم المستخدم الخاص بك: `{user.username}`

⚠️ لا تشارك هذا الرمز مع أحد!
!السكربت رح يشتغل تلقائيًا على موقع stake.com ويجرب الأكواد كل 3 ثواني."""

                # - إنشاء السكربت الكامل مع الرمز والاسم -
                # ******************* مهم جداً *******************
                # هذا هو السكربت الكامل. تأكد إنو منسخ بشكل صحيح.
                # ************************************************
                # الحصول على رابط السيرفر من متغير البيئة أو استخدام الافتراضي
                server_url_for_script = os.environ.get('SCRIPT_SERVER_URL') or "http://127.0.0.1:5000"
                
                script_content = f"""// ==UserScript==
// @name Stake Code Auto Claimer Top Bar
// @namespace http://tampermonkey.net/
// @version 3.11
// @description Top bar interface with improved claiming - UI unchanged
// @author StakeBot
// @match https://stake.com/*
// @grant GM_xmlhttpRequest
// @grant GM_addStyle
// @connect localhost
// @connect 127.0.0.1
// ==/UserScript==

(function() {{
    'use strict';

    // الرمز الخاص بالمستخدم - تم تحديثه من البوت
    const SCRIPT_TOKEN = "{user.script_token}";
    const SERVER_URL = "{server_url_for_script}"; // <-- رابط السيرفر من متغير البيئة

    // اسم المستخدم - تم تحديثه من البوت
    const USERNAME = "{user.username}";

    // متغيرات النظام
    let isClaiming = false;
    let claimHistory = [];
    let autoClaimEnabled = false;
    let soundEnabled = true;

    // إنشاء أنماط CSS للواجهة العلوية الكاملة (دون تعديل على الشكل)
    function createTopBarStyles() {{
        GM_addStyle(`/* شريط الأدوات العلوي الكامل */
#stake-top-toolbar {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    background: linear-gradient(90deg, #0d1b2a, #1b263b);
    color: #e0f7fa;
    padding: 8px 15px;
    z-index: 10001;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    box-shadow: 0 2px 10px rgba(0,0,0,0.5);
    border-bottom: 2px solid #4caf50;
    backdrop-filter: blur(10px);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12px;
}}

/* تحريك المحتوى الأساسي للأسفل */
body {{
    padding-top: 45px !important;
    margin-top: 0 !important;
}}

#stake-toolbar-left {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

#stake-toolbar-right {{
    display: flex;
    align-items: center;
    gap: 10px;
}}

.toolbar-section {{
    display: flex;
    align-items: center;
    gap: 8px;
}}

.toolbar-user-info {{
    background: rgba(76, 175, 80, 0.2);
    padding: 4px 10px;
    border-radius: 15px;
    border: 1px solid #4caf50;
    font-size: 11px;
    font-weight: 600;
    color: #4caf50;
}}

.toolbar-title {{
    font-size: 16px;
    font-weight: bold;
    color: #4caf50;
    text-shadow: 0 0 5px rgba(76, 175, 80, 0.5);
    display: flex;
    align-items: center;
    gap: 8px;
}}

.toolbar-btn {{
    background: linear-gradient(45deg, #2196f3, #1976d2);
    color: white;
    border: none;
    padding: 5px 12px;
    border-radius: 15px;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    transition: all 0.2s ease;
    border: 1px solid rgba(255,255,255,0.2);
    white-space: nowrap;
    box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}}

.toolbar-btn:hover {{
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}}

.toolbar-btn.success {{
    background: linear-gradient(45deg, #4caf50, #388e3c);
    border-color: #4caf50;
}}

.toolbar-btn.warning {{
    background: linear-gradient(45deg, #ff9800, #f57c00);
    border-color: #ff9800;
}}

.toolbar-btn.danger {{
    background: linear-gradient(45deg, #f44336, #d32f2f);
    border-color: #f44336;
}}

.toolbar-btn:disabled {{
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}}

.toolbar-toggle {{
    position: relative;
    display: inline-block;
    width: 34px;
    height: 20px;
}}

.toolbar-toggle input {{
    opacity: 0;
    width: 0;
    height: 0;
}}

.toolbar-slider {{
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: #ccc;
    transition: .4s;
    border-radius: 20px;
}}

.toolbar-slider:before {{
    position: absolute;
    content: "";
    height: 16px;
    width: 16px;
    left: 2px;
    bottom: 2px;
    background-color: white;
    transition: .4s;
    border-radius: 50%;
}}

input:checked + .toolbar-slider {{
    background-color: #2196F3;
}}

input:checked + .toolbar-slider:before {{
    transform: translateX(14px);
}}

.toolbar-status-text {{
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
    color: #e0f7fa;
}}

.status-indicator-top {{
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background-color: #90a4ae;
    margin-left: 5px;
    vertical-align: middle;
}}

.status-indicator-top.active {{
    background-color: #4caf50;
    box-shadow: 0 0 8px #4caf50;
}}

.status-indicator-top.claiming {{
    background-color: #ff9800;
    box-shadow: 0 0 8px #ff9800;
    animation: pulse 1.5s infinite;
}}

@keyframes pulse {{
    0% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
    100% {{ opacity: 1; }}
}}

.toolbar-history {{
    position: absolute;
    top: 45px;
    left: 15px;
    background: #1b263b;
    color: #e0f7fa;
    padding: 15px;
    border-radius: 8px;
    z-index: 10000;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    border: 1px solid #4caf50;
    min-width: 280px;
    max-width: 400px;
    max-height: 300px;
    overflow-y: auto;
    display: none;
    font-size: 11px;
}}

.history-item-top {{
    padding: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.15);
    font-size: 10px;
}}

.history-item-top:last-child {{
    border-bottom: none;
}}

.code-value-top {{
    color: #4caf50;
    font-weight: 600;
    font-size: 11px;
}}

#close-history-top {{
    background: #f44336;
    border: none;
    color: white;
    cursor: pointer;
    font-size: 14px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
}}

/* تحسينات للشاشات الصغيرة */
@media (max-width: 768px) {{
    #stake-top-toolbar {{
        flex-direction: column;
        align-items: flex-start;
        gap: 8px;
    }}

    #stake-toolbar-left, #stake-toolbar-right {{
        width: 100%;
        justify-content: space-between;
    }}
}}
`);
    }}

    // إنشاء شريط الأدوات العلووي الكامل (دون تعديل على الشكل)
    function createTopToolbar() {{
        // التأكد من أن العنصر ما موجود من قبل
        if (document.getElementById('stake-top-toolbar')) {{
            return;
        }}

        const toolbar = document.createElement('div');
        toolbar.id = 'stake-top-toolbar';
        toolbar.innerHTML = `
            <div id="stake-toolbar-left">
                <div class="toolbar-title">🎯 Stake Claimer</div>
                <div class="toolbar-user-info">👤 {USERNAME}</div>
                <div class="toolbar-section">
                    <span style="font-size: 11px; font-weight: 600;">📡:</span>
                    <span id="top-status-text" class="toolbar-status-text">جاري التحقق...</span>
                    <span id="top-status-indicator" class="status-indicator-top"></span>
                </div>
            </div>
            <div id="stake-toolbar-right">
                <button id="manual-claim-top" class="toolbar-btn">🔁 فحص يدوي</button>
                <button id="turbo-claim-top" class="toolbar-btn danger">🚀 Turbo</button>
                <div class="toolbar-section">
                    <span style="font-size: 11px; font-weight: 600;">🔊:</span>
                    <button id="toggle-sound-top" class="toolbar-btn">مفعل</button>
                </div>
                <div class="toolbar-section">
                    <span style="font-size: 11px; font-weight: 600;">⚡:</span>
                    <label class="toolbar-toggle">
                        <input type="checkbox" id="auto-claim-toggle-top">
                        <span class="toolbar-slider"></span>
                    </label>
                    <button id="toggle-auto-claim-top" class="toolbar-btn warning">تفعيل</button>
                </div>
                <button id="show-history-top" class="toolbar-btn">📜 السجل</button>
            </div>
        `;

        document.body.insertBefore(toolbar, document.body.firstChild);

        // إضافة مستمعات الأحداث
        document.getElementById('manual-claim-top').addEventListener('click', checkForNewCodes);
        document.getElementById('turbo-claim-top').addEventListener('click', turboClaim);
        document.getElementById('toggle-sound-top').addEventListener('click', toggleSound);
        document.getElementById('auto-claim-toggle-top').addEventListener('change', toggleAutoClaimFromSwitch);
        document.getElementById('toggle-auto-claim-top').addEventListener('click', toggleAutoClaim);
        document.getElementById('show-history-top').addEventListener('click', showHistory);
    }}

    // إنشاء نافذة السجل (دون تعديل على الشكل)
    function createHistoryPanel() {{
        // التأكد من أن العنصر ما موجود من قبل
        if (document.getElementById('toolbar-history-panel')) {{
            return;
        }}

        const historyPanel = document.createElement('div');
        historyPanel.id = 'toolbar-history-panel';
        historyPanel.className = 'toolbar-history';
        historyPanel.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <strong style="font-size: 13px; color: #4caf50;">📜 سجل المطالبات</strong>
                <button id="close-history-top">×</button>
            </div>
            <div id="history-content-top" style="max-height: 240px; overflow-y: auto;">
                <div style="text-align: center; color: #90a4ae; padding: 15px;">لا توجد مطالبات بعد</div>
            </div>
        `;

        document.body.appendChild(historyPanel);

        // إضافة مستمع لإغلاق النافذة
        document.getElementById('close-history-top').addEventListener('click', hideHistory);
    }}

    // تفعيل/إيقاف المطالبة التلقائية من الزر
    function toggleAutoClaim() {{
        autoClaimEnabled = !autoClaimEnabled;
        document.getElementById('auto-claim-toggle-top').checked = autoClaimEnabled;
        updateAutoClaimButton();
        updateStatus(autoClaimEnabled ? 'المطالبة التلقائية مفعلة' : 'المطالبة التلقائية معطلة', autoClaimEnabled ? 'active' : 'normal');
    }}

    // تفعيل/إيقاف المطالبة التلقائية من الزر التبديلي
    function toggleAutoClaimFromSwitch() {{
        autoClaimEnabled = this.checked;
        updateAutoClaimButton();
        updateStatus(autoClaimEnabled ? 'المطالبة التلقائية مفعلة' : 'المطالبة التلقائية معطلة', autoClaimEnabled ? 'active' : 'normal');
    }}

    // تحديث زر المطالبة التلقائية
    function updateAutoClaimButton() {{
        const toggleBtn = document.getElementById('toggle-auto-claim-top');
        if (toggleBtn) {{
            toggleBtn.textContent = autoClaimEnabled ? 'إيقاف' : 'تفعيل';
            toggleBtn.className = autoClaimEnabled ? 'toolbar-btn success' : 'toolbar-btn warning';
        }}
    }}

    // تحديث زر الأصوات
    function updateSoundButton() {{
        const soundBtn = document.getElementById('toggle-sound-top');
        if (soundBtn) {{
            soundBtn.textContent = soundEnabled ? 'مفعل' : 'معطل';
            soundBtn.className = soundEnabled ? 'toolbar-btn' : 'toolbar-btn danger';
        }}
    }}

    // تحديث الحالة
    function updateStatus(text, status = 'normal') {{
        const statusText = document.getElementById('top-status-text');
        const indicator = document.getElementById('top-status-indicator');

        if (statusText) statusText.textContent = text;
        if (indicator) {{
            indicator.className = 'status-indicator-top';
            if (status === 'active') indicator.classList.add('active');
            if (status === 'claiming') indicator.classList.add('claiming');
        }}
    }}

    // إضافة إلى سجل المطالبات
    function addToHistory(code, value, status) {{
        claimHistory.unshift({{
            code: code,
            value: value,
            status: status,
            timestamp: new Date()
        }});

        if (claimHistory.length > 50) {{
            claimHistory.pop();
        }}
    }}

    // عرض السجل
    function showHistory() {{
        const historyPanel = document.getElementById('toolbar-history-panel');
        const historyContent = document.getElementById('history-content-top');

        if (historyPanel && historyContent) {{
            historyPanel.style.display = 'block';

            if (claimHistory.length === 0) {{
                historyContent.innerHTML = '<div style="text-align: center; color: #90a4ae; padding: 15px;">لا توجد مطالبات بعد</div>';
            }} else {{
                historyContent.innerHTML = claimHistory.map(item => `
                    <div class="history-item-top">
                        <div><strong style="font-size: 11px;">${{item.code}}</strong> - <span class="code-value-top">$${{item.value}}</span></div>
                        <div style="color: ${{item.status === 'success' ? '#4caf50' : '#f44336'}}; font-size: 9px; margin-top: 3px;">
                            ${{item.status === 'success' ? '✅ نجح' : '❌ فشل'}} - ${{item.timestamp.toLocaleTimeString('ar-SA')}}
                        </div>
                    </div>
                `).join('');
            }}
        }}
    }}

    // إخفاء السجل
    function hideHistory() {{
        const historyPanel = document.getElementById('toolbar-history-panel');
        if (historyPanel) {{
            historyPanel.style.display = 'none';
        }}
    }}

    // تفعيل/إيقاف المطالبة التلقائية
    function toggleAutoClaim() {{
        autoClaimEnabled = !autoClaimEnabled;
        updateAutoClaimButton();
        if (autoClaimEnabled) {{
            updateStatus('المطالبة التلقائية مفعلة', 'active');
            // فحص فوري عند التفعيل
            setTimeout(checkForNewCodes, 500);
        }} else {{
            updateStatus('المطالبة التلقائية معطلة', 'normal');
        }}
    }}

    // تفعيل/إيقاف الأصوات
    function toggleSound() {{
        soundEnabled = !soundEnabled;
        updateSoundButton();
    }}

    // تشغيل الصوت
    function playSound(type) {{
        if (!soundEnabled) return;

        let audio;
        switch(type) {{
            case 'new_code':
                // صوت مخصص للكود الجديد
                audio = new Audio("audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFfHl8f4B/gH9/fn18e3t8fHx9fX5/gIGCg4SFhoeIiYqLjI2Oj5CRkpOUlZaXmJmam5ydnp+goaKjpKWmp6ipqqusra6vsLGys7S1tre4ubq7vL2+v8DBwsPExcbHyMnKy8zNzs/Q0dLT1NXW19jZ2tvc3d7f4OHi4+Tl5ufo6err7O3u7/Dx8vP09fb3+Pn6+/z9/v8AAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4/QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl9gYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXp7fH1+f4CBgoOEhYaHiImKi4yNjo+QkZKTlJWWl5iZmpucnZ6foKGio6SlpqeoqaqrrK2ur7CxsrO0tba3uLm6u7y9vr/AwcLDxMXGx8jJysvMzc7P0NHS09TV1tfY2drb3N3e3+Dh4uPk5ebn6Onq6+zt7u/w8fLz9PX29/j5+vv8/f7/");
                break;
            case 'success':
                // صوت مخصص للنجاح
                audio = new Audio("audio/wav;base64,UklGRlwGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQgGAACBhYqFfHl8f4B/gH9/fn18e3t8fHx9fX5/gIGCg4SFhoeIiYqLjI2Oj5CRkpOUlZaXmJmam5ydnp+goaKjpKWmp6ipqqusra6vsLGys7S1tre4ubq7vL2+v8DBwsPExcbHyMnKy8zNzs/Q0dLT1NXW19jZ2tvc3d7f4OHi4+Tl5ufo6err7O3u7/Dx8vP09fb3+Pn6+/z9/v8AAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4/QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl9gYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXp7fH1+f4CBgoOEhYaHiImKi4yNjo+QkZKTlJWWl5iZmpucnZ6foKGio6SlpqeoqaqrrK2ur7CxsrO0tba3uLm6u7y9vr/AwcLDxMXGx8jJysvMzc7P0NHS09TV1tfY2drb3N3e3+Dh4uPk5ebn6Onq6+zt7u/w8fLz9PX29/j5+vv8/f7/");
                break;
            case 'error':
                // صوت مخصص للخطأ
                audio = new Audio("audio/wav;base64,UklGRlwGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQgGAACBhYqFfHl8f4B/gH9/fn18e3t8fHx9fX5/gIGCg4SFhoeIiYqLjI2Oj5CRkpOUlZaXmJmam5ydnp+goaKjpKWmp6ipqqusra6vsLGys7S1tre4ubq7vL2+v8DBwsPExcbHyMnKy8zNzs/Q0dLT1NXW19jZ2tvc3d7f4OHi4+Tl5ufo6err7O3u7/Dx8vP09fb3+Pn6+/z9/v8AAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4/QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl9gYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXp7fH1+f4CBgoOEhYaHiImKi4yNjo+QkZKTlJWWl5iZmpucnZ6foKGio6SlpqeoqaqrrK2ur7CxsrO0tba3uLm6u7y9vr/AwcLDxMXGx8jJysvMzc7P0NHS09TV1tfY2drb3N3e3+Dh4uPk5ebn6Onq6+zt7u/w8fLz9PX29/j5+vv8/f7/");
                break;
            default:
                return;
        }}
        audio.play().catch(e => console.log('🔇 خطأ في تشغيل الصوت:', e));
    }}

    // التحقق من الأكواد الجديدة
    function checkForNewCodes() {{
        if (isClaiming) {{
            updateStatus('عملية مطالبة جارية...', 'claiming');
            return;
        }}
        updateStatus('جاري الفحص...', 'claiming');

        GM_xmlhttpRequest({{
            method: 'GET',
            url: `${{SERVER_URL}}/api/codes/pending`,
            headers: {{
                'Script-Token': SCRIPT_TOKEN,
                'Content-Type': 'application/json'
            }},
            onload: function(response) {{
                try {{
                    if (response.status === 401) {{
                        updateStatus('اشتراك غير مفعل', 'error');
                        playSound('error');
                        alert('❌ اشتراكك غير مفعل أو انتهت صلاحيته.');
                        return;
                    }}
                    const data = JSON.parse(response.responseText);
                    if (data.length > 0) {{
                        playSound('new_code');
                        processCode(data[0]);
                    }} else {{
                        updateStatus('متصل - لا توجد أكواد', 'active');
                    }}
                }} catch (e) {{
                    console.error('خطأ في تحليل البيانات:', e);
                    updateStatus('خطأ في البيانات', 'error');
                    playSound('error');
                }}
            }},
            onerror: function(error) {{
                console.error('خطأ في الاتصال بالسيرفر:', error);
                updateStatus('خطأ في الاتصال', 'error');
                playSound('error');
            }}
        }});
    }}

    // محاكاة إدخال الكود في الموقع بشكل فعلي (محسّنة)
    function simulateCodeEntry(code) {{
        return new Promise((resolve, reject) => {{
            console.log(`🎯 محاولة إدخال الكود: ${{code}}`);

            // البحث عن حقول الإدخال حسب الاسم والقسم (من السكربت القديم)
            let codeInput = null;
            const inputs = Array.from(document.querySelectorAll('input[name="code"]'));
            for (const inp of inputs) {{
                const section = inp.closest('section') || inp.closest('div');
                if (section && section.innerText.includes("توزيع المكافآت")) {{
                    if (inp.offsetParent !== null && !inp.disabled && !inp.readOnly) {{
                        codeInput = inp;
                        break;
                    }}
                }}
            }}

            // إذا ما لقى الحقل حسب الاسم، يجرب الطرق القديمة
            if (!codeInput) {{
                const inputSelectors = [
                    'input[name="code"]',
                    'input[placeholder*="code"]',
                    'input[placeholder*="كود"]',
                    'input[type="text"]'
                ];

                outerLoop: for (let selector of inputSelectors) {{
                    const inputs = document.querySelectorAll(selector);
                    for (let input of inputs) {{
                        const section = input.closest('section') || input.closest('div');
                        if (section && section.innerText.includes("توزيع المكافآت") &&
                            input.offsetParent !== null && !input.disabled && !input.readOnly) {{
                            codeInput = input;
                            break outerLoop;
                        }}
                    }}
                }}
            }}

            if (codeInput) {{
                // مسح أي قيمة سابقة
                codeInput.value = '';
                // كتابة الكود
                codeInput.focus();
                codeInput.value = code;
                // تشغيل الأحداث علشان الموقع يحس بالتغيير
                codeInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                codeInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                console.log(`✅ تم إدخال الكود في الحقل:`, codeInput);
                // الانتظار قليل علشان الموقع يعالج الإدخال
                setTimeout(() => {{
                    resolve(codeInput);
                }}, 500);
            }} else {{
                console.error('❌ ما لقينا حقل إدخال الكود');
                reject(new Error('ما لقينا حقل إدخال الكود'));
            }}
        }});
    }}

    // دالة محسّنة للضغط على زر الإرسال
    function clickSubmitButton() {{
        return new Promise((resolve) => {{
            console.log('👆 محاولة الضغط على زر الإرسال');

            // البحث عن زر "إرسال" في قسم "توزيع المكافآت" (من السكربت القديم)
            const allButtons = Array.from(document.querySelectorAll('button'));
            const sendButtons = allButtons.filter(btn =>
                btn.innerText && btn.innerText.trim() === "إرسال"
            );

            let submitButton = null;
            for (const btn of sendButtons) {{
                const section = btn.closest('section') || btn.closest('div');
                if (section && section.innerText.includes("توزيع المكافآت")) {{
                    submitButton = btn;
                    break;
                }}
            }}

            // إذا ما لقى الزر حسب النص، يجرب الطرق القديمة
            if (!submitButton) {{
                const submitSelectors = [
                    'button[type="submit"]',
                    'button[class*="submit"]',
                    'button[class*="claim"]',
                    'button[class*="send"]',
                    'button'
                ];

                for (let selector of submitSelectors) {{
                    const buttons = document.querySelectorAll(selector);
                    for (let button of buttons) {{
                        const text = (button.textContent || button.innerText || '').toLowerCase();
                        if (button.offsetParent !== null &&
                            (text.includes('submit') || text.includes('إرسال') ||
                             text.includes('claim') || text.includes('مطالبة') ||
                             text.includes('send'))) {{
                            submitButton = button;
                            break;
                        }}
                    }}
                    if (submitButton) break;
                }}
            }}

            if (submitButton) {{
                submitButton.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                setTimeout(() => {{
                    submitButton.click();
                    console.log(`✅ ضغطت على زر الإرسال:`, submitButton.textContent || submitButton.innerText);
                    resolve(true);
                }}, 300);
            }} else {{
                console.error('❌ ما لقينا زر الإرسال');
                resolve(false);
            }}
        }});
    }}

    // دالة محسّنة لاختيار العملة
    function selectCurrency(currency = 'USDT') {{
        return new Promise((resolve) => {{
            console.log(`💱 محاولة اختيار العملة: ${{currency}}`);

            // البحث عن العملة حسب النص (من السكربت القديم)
            let currencyElement = null;
            const currencyTexts = [currency, 'USDT', 'Tether', 'تذكرة'];
            const allSelects = Array.from(document.querySelectorAll('select, div[role="button"], button'));

            for (let text of currencyTexts) {{
                for (let select of allSelects) {{
                    const selectText = (select.textContent || select.innerText || '').trim();
                    if (select.offsetParent !== null && selectText.includes(text)) {{
                        currencyElement = select;
                        break;
                    }}
                }}
                if (currencyElement) break;
            }}

            // إذا ما لقى العملة حسب النص، يجرب الطرق القديمة
            if (!currencyElement) {{
                const selectSelectors = [
                    'select[name*="currency"]',
                    'select[id*="currency"]',
                    'div[role="button"]',
                    'button'
                ];

                outerLoop: for (let selector of selectSelectors) {{
                    const selects = document.querySelectorAll(selector);
                    for (let select of selects) {{
                        if (select.offsetParent !== null) {{
                            currencyElement = select;
                            break outerLoop;
                        }}
                    }}
                }}
            }}

            if (currencyElement) {{
                currencyElement.scrollIntoView({{ behavior: 'smooth', block: 'center' }});

                setTimeout(() => {{
                    currencyElement.click();
                    console.log(`✅ تم اختيار العملة: ${{currency}}`);
                    resolve(true);
                }}, 300);
            }} else {{
                console.log('⚠️ ما لقينا العملة، بنساوي على القيمة الافتراضية');
                resolve(false);
            }}
        }});
    }}

    // معالجة الكود (محسّنة)
    function processCode(codeData) {{
        if (isClaiming) return;
        isClaiming = true;
        updateStatus(`جاري معالجة الكود: ${{codeData.code}}`, 'claiming');
        playSound('new_code');

        // تنفيذ الخطوات بالترتيب
        simulateCodeEntry(codeData.code)
        .then(() => {{
            // الخطوة 1: إدخال الكود وإرساله
            return clickSubmitButton();
        }})
        .then((success) => {{
            if (!success) throw new Error('فشل الضغط على زر الإرسال الأول');
            // الخطوة 2: الانتظار قليل علشان تظهر نافذة اختيار العملة
            return new Promise(resolve => setTimeout(resolve, 1500));
        }})
        .then(() => {{
            // الخطوة 3: اختيار العملة
            return selectCurrency('USDT');
        }})
        .then(() => {{
            // الخطوة 4: الانتظار قليل ثم الضغط على إرسال مرة ثانية
            return new Promise(resolve => setTimeout(resolve, 1000));
        }})
        .then(() => {{
            // الضغط على زر الإرسال الثاني (إذا لازم)
            return clickSubmitButton();
        }})
        .then(() => {{
            // الخطوة 5: إرسال نتيجة العملية للسيرفر
            return sendCodeValue(codeData.id, codeData.value || 0, codeData.code);
        }})
        .then(() => {{
            updateStatus(`✅ تم استخدام الكود: ${{codeData.code}}`, 'active');
            addToHistory(codeData.code, codeData.value || 0, 'success');
            playSound('success');
            isClaiming = false;
            // إذا كانت المطالبة التلقائية مفعلة، نستمر في الفحص
            if (autoClaimEnabled) {{
                setTimeout(checkForNewCodes, 1000);
            }}
        }})
        .catch((error) => {{
            console.error('خطأ في معالجة الكود:', error);
            updateStatus(`❌ خطأ: ${{error.message}}`, 'error');
            addToHistory(codeData.code, codeData.value || 0, 'error');
            playSound('error');
            isClaiming = false;
            // إذا كانت المطالبة التلقائية مفعلة، نكمل الفحص
            if (autoClaimEnabled) {{
                setTimeout(checkForNewCodes, 3000);
            }}
        }});
    }}

    // إرسال قيمة الكود المستخدم للسيرفر
    function sendCodeValue(codeId, value, code) {{
        return new Promise((resolve, reject) => {{
            GM_xmlhttpRequest({{
                method: 'POST',
                url: `${{SERVER_URL}}/api/codes/${{codeId}}/claim`,
                headers: {{
                    'Script-Token': SCRIPT_TOKEN,
                    'Content-Type': 'application/json'
                }},
                data: JSON.stringify({{
                    value: value,
                    currency: 'USDT',
                    code: code
                }}),
                onload: function(response) {{
                    if (response.status === 200) {{
                        console.log(`✅ تم إرسال قيمة الكود للسيرفر: ${{value}} USD`);
                        resolve();
                    }} else {{
                        console.error(`❌ خطأ في إرسال قيمة الكود للسيرفر. الحالة: ${{response.status}}`);
                        reject(new Error(`خطأ في إرسال قيمة الكود للسيرفر: ${{response.status}}`));
                    }}
                }},
                onerror: function(error) {{
                    console.error('❌ خطأ في الاتصال بالسيرفر لإرسال قيمة الكود:', error);
                    reject(new Error('خطأ في الاتصال بالسيرفر لإرسال قيمة الكود'));
                }}
            }});
        }});
    }}

    // التحقق من صحة الرمز
    function validateToken() {{
        return new Promise((resolve, reject) => {{
            GM_xmlhttpRequest({{
                method: 'POST',
                url: `${{SERVER_URL}}/api/validate-token`,
                headers: {{
                    'Content-Type': 'application/json'
                }},
                data: JSON.stringify({{
                    token: SCRIPT_TOKEN
                }}),
                onload: function(response) {{
                    try {{
                        const data = JSON.parse(response.responseText);
                        if (data.valid) {{
                            console.log('✅ الرمز صحيح واشتراك ساري');
                            resolve();
                        }} else {{
                            console.error('❌ الرمز غير صحيح أو اشتراك غير مفعل:', data.message);
                            reject(new Error(data.message));
                        }}
                    }} catch (e) {{
                        console.error('❌ خطأ في تحليل رد التحقق من الرمز:', e);
                        reject(new Error('خطأ في التحقق من الرمز'));
                    }}
                }},
                onerror: function(error) {{
                    console.error('❌ خطأ في الاتصال بالسيرفر للتحقق من الرمز:', error);
                    reject(new Error('خطأ في الاتصال بالسيرفر'));
                }}
            }});
        }});
    }}

    // مطالبة Turbo (معالجة 5 أكواد متتالية بسرعة)
    function turboClaim() {{
        if (isClaiming) {{
            alert('⚠️ هناك عملية مطالبة جارية حالياً!');
            return;
        }}

        let turboCount = 0;
        const maxTurbo = 5;

        function doTurboClaim() {{
            if (turboCount >= maxTurbo || !autoClaimEnabled) {{
                updateStatus(`🚀 Turbo انتهى - تم معالجة ${{turboCount}} أكواد`, 'active');
                return;
            }}

            GM_xmlhttpRequest({{
                method: 'GET',
                url: `${{SERVER_URL}}/api/codes/pending`,
                headers: {{
                    'Script-Token': SCRIPT_TOKEN,
                    'Content-Type': 'application/json'
                }},
                onload: function(response) {{
                    try {{
                        if (response.status === 401) {{
                            updateStatus('اشتراك غير مفعل', 'error');
                            playSound('error');
                            return;
                        }}
                        const data = JSON.parse(response.responseText);
                        if (data.length > 0) {{
                            playSound('new_code');
                            turboCount++;
                            updateStatus(`🚀 Turbo: ${{turboCount}}/${{maxTurbo}} - ${{data[0].code}}`, 'claiming');
                            
                            // معالجة الكود بدون إرسال النتيجة للسيرفر (علشان السرعة)
                            simulateCodeEntry(data[0].code)
                                .then(() => clickSubmitButton())
                                .then((success) => {{
                                    if (success) {{
                                        addToHistory(data[0].code, data[0].value || 0, 'success');
                                    }} else {{
                                        addToHistory(data[0].code, data[0].value || 0, 'error');
                                    }}
                                    // الانتقال للكود التالي فوراً
                                    setTimeout(doTurboClaim, 500);
                                }})
                                .catch((error) => {{
                                    console.error('خطأ في Turbo:', error);
                                    addToHistory(data[0].code, data[0].value || 0, 'error');
                                    setTimeout(doTurboClaim, 500);
                                }});
                        }} else {{
                            updateStatus(`🚀 Turbo: لا توجد أكواد (${{turboCount}}/${{maxTurbo}})`, 'active');
                        }}
                    }} catch (e) {{
                        console.error('خطأ في Turbo:', e);
                        setTimeout(doTurboClaim, 1000);
                    }}
                }},
                onerror: function(error) {{
                    console.error('خطأ في Turbo:', error);
                    setTimeout(doTurboClaim, 1000);
                }}
            }});
        }}

        updateStatus('🚀 بدء Turbo Claim...', 'claiming');
        doTurboClaim();
    }}

    // انتظار تحميل الصفحة بالكامل
    function waitForPageLoad() {{
        return new Promise((resolve) => {{
            if (document.readyState === 'complete') {{
                resolve();
            }} else {{
                window.addEventListener('load', resolve);
            }}
        }});
    }}

    // بدء التشغيل
    async function init() {{
        try {{
            // انتظار تحميل الصفحة بالكامل
            await waitForPageLoad();
            // انتظار إضافي للتأكد من تحميل المحتوى
            await new Promise(resolve => setTimeout(resolve, 1500));

            createTopBarStyles();
            createTopToolbar(); // إنشاء شريط الأدوات العلوي
            createHistoryPanel(); // إنشاء نافذة السجل

            // التحقق من صحة الرمز
            validateToken().then(() => {{
                updateStatus('متصل ومفعل', 'active');
                playSound('success');
                // بدء الفحص الدوري كل 3 ثوانٍ إذا كانت المطالبة التلقائية مفعلة
                setInterval(() => {{
                    if (autoClaimEnabled) {{
                        checkForNewCodes();
                    }}
                }}, 3000);
                // فحص فوري عند التحميل
                setTimeout(checkForNewCodes, 1000);
                console.log('🎯 Stake Code Claimer Top Bar تم تفعيله بنجاح');
            }}).catch((error) => {{
                updateStatus('غير مفعل', 'error');
                playSound('error');
                alert(`❌ خطأ في تفعيل السكربت: ${{error.message}}يرجى التأكد من اشتراكك.`);
                console.error('خطأ في التحقق من الرمز:', error);
            }});
        }} catch (error) {{
            console.error('خطأ في تهيئة السكربت:', error);
        }}
    }}

    // تشغيل السكربت بعد تأخير صغير للتأكد من تحميل الصفحة
    setTimeout(init, 2500);
}})();
"""

                # إرسال رسالة المعلومات أولاً
                bot.reply_to(message, script_info, parse_mode='Markdown', reply_markup=main_menu_keyboard())

                # إنشاء ملف مؤقت ورفعه
                try:
                    # إنشاء ملف مؤقت في الذاكرة
                    script_file = io.BytesIO(script_content.encode('utf-8'))
                    # تحديد اسم الملف المرفق
                    script_file.name = f"stake_claimer_{user.username}.user.js"

                    # إرسال الملف كمرفق
                    bot.send_document(
                        message.chat.id,
                        script_file,
                        caption=f"📥 ملف السكربت الخاص بك، {user.username}\nاضغط على الملف وTampermonkey رح يكتشفه تلقائيًا!",
                        reply_markup=main_menu_keyboard()
                    )
                    print(f"[📤] تم إرسال ملف السكربت لـ {user.username} ({user_id})")
                except Exception as file_error:
                    print(f"[❌] خطأ في إرسال ملف السكربت: {file_error}")
                    import traceback
                    print(traceback.format_exc())
                    # إذا في مشكلة في إرسال الملف، نبعت رسالة خطأ واضحة
                    bot.reply_to(message, "❌ حدث خطأ أثناء إرسال ملف السكربت. يرجى المحاولة لاحقاً.", reply_markup=main_menu_keyboard())

            else:
                bot.reply_to(message, "❌ لم يتم العثور على معلومات المستخدم.", reply_markup=main_menu_keyboard())
    except Exception as e:
        print(f"[💥] خطأ في handle_get_script: {e}")
        import traceback
        print(traceback.format_exc())
        bot.reply_to(message, "❌ حدث خطأ أثناء إرسال السكربت. يرجى المحاولة لاحقاً.", reply_markup=main_menu_keyboard())

# -

# - تعديل دالة حسابي علشان تتحقق من الاشتراك -
@bot.message_handler(func=lambda message: message.text == '👤 حسابي')
@bot.message_handler(commands=['status'])
def handle_profile(message):
    """عرض معلومات الحساب"""
    try:
        user_id = str(message.from_user.id)
        with app.app_context():
            user = User.query.filter_by(user_id=user_id).first()
            if user:
                # - التحقق من الاشتراك -
                if not is_user_subscribed(user_id):
                    bot.reply_to(message, "❌ لازم يكون عندك اشتراك شغال علشان تشوف معلومات الحساب. استخدم '🎟️ استبدال كود'.", reply_markup=main_menu_keyboard())
                    return
                # -
                
                # تحديد حالة الاشتراك
                if user.is_active and user.subscription_end > datetime.utcnow():
                    subscription_status = f"🟢 مفعل حتى: {user.subscription_end.strftime('%Y-%m-%d %H:%M')}"
                elif user.is_active:
                    subscription_status = "🟡 مفعل بس انتهت صلاحيته"
                else:
                    subscription_status = "🔴 غير مفعل"

                status_text = f"""👤 *معلومات حسابك:*
🆔 معرف التليغرام: `{user.user_id}`
👤 اسم المستخدم: `{user.username or 'غير مسجل'}`
📅 تاريخ التسجيل: {user.created_at.strftime('%Y-%m-%d')}
🔐 رمز السكربت: `{user.script_token}`
💳 رصيدك: {user.balance:.2f} USD
📅 حالة الاشتراك: {subscription_status}"""
                bot.reply_to(message, status_text, parse_mode='Markdown', reply_markup=main_menu_keyboard())
            else:
                bot.reply_to(message, "❌ لم يتم العثور على معلومات حسابك. يرجى التسجيل أولاً.", reply_markup=main_menu_keyboard())
    except Exception as e:
        print(f"Error in handle_profile: {e}")
        bot.reply_to(message, "❌ حدث خطأ أثناء جلب معلومات الحساب.", reply_markup=main_menu_keyboard())

# -

# نسخهم أو نكتب نسخة بسيطة منها إذا لزم.
# -
if __name__ == '__main__':
    print("🚀 بوت تلغرام Stake Code Claimer يعمل...")
    bot.polling()
