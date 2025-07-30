# monitor_bot.py (الآمن - بدون توكنات)
import asyncio
import logging
import os
import re
import tempfile
import requests
from datetime import datetime
from telethon import TelegramClient, events
import cv2
import pytesseract
from PIL import Image

# - إعداد التسجيل (Logging) -
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler() # طباعة الرسائل في الكونسول
        # logging.FileHandler('monitor.log') # يمكنك إلغاء التعليق هنا علشان تحفظ الرسائل في ملف
    ]
)
logger = logging.getLogger(__name__)

# - إعدادات Telethon -
# استبدل القيم التالية بقيمك الخاصة من https://my.telegram.org
# استخدم متغيرات بيئة علشان الأمان
API_ID = os.environ.get('API_ID') # <-- استخدم متغير بيئة
API_HASH = os.environ.get('API_HASH') # <-- استخدم متغير بيئة

if not API_ID or not API_HASH:
    raise ValueError("❌ API_ID و API_HASH مش محددين. لازم تحدد في متغيرات البيئة.")

# - إعدادات القنوات -
# قناة MyStakeCodes007 (المعدّل)
CHANNEL_TO_POST = os.environ.get('CHANNEL_TO_POST') or '@Stakecodday' # <-- استخدم متغير بيئة

# القنوات المراقبة
WATCHED_CHANNELS = os.environ.get('WATCHED_CHANNELS')
if WATCHED_CHANNELS:
    WATCHED_CHANNELS = [ch.strip() for ch in WATCHED_CHANNELS.split(',')]
else:
    WATCHED_CHANNELS = [
        "Stakewpi",
        "StakeBonusCodeVIP", 
        "StakecomDailyDrops",
        "stakeimgantengofficial",
        "stakebonusdrops"
    ]

# - عنوان السيرفر للإرسال إليه -
SERVER_URL = os.environ.get('MONITOR_SERVER_URL') or 'http://127.0.0.1:5000' # <-- استخدم متغير بيئة

# - أنماط متعددة لاستخراج الأكواد - محسّنة -
# الأنماط الأكثر تحديداً أولاً
CODE_PATTERNS = [
    r'\b(STAKECOM[A-Z0-9]{6,15})\b',
    r'\b(stakecom[a-z0-9]{6,15})\b',
    r '\b(STK[A-Z0-9]{4,12})\b',
    r '\b(stk[a-z0-9]{4,12})\b',
    r '(?:[Rr]eward|[Cc]ode)[:\s]*([A-Za-z0-9]{6,20})',
    # أنماط أكثر عمومية كاحتياطية
    r '\b([A-Z0-9]{8,20})\b', # أكواد كبيرة بالأحرف الكبيرة والأرقام فقط
    r '\b([A-Za-z0-9]{10,25})\b' # أنماط عشوائية أطول
]

# أنماط لاستخراج القيمة
VALUE_PATTERNS = [
    r '(?:value|قيمة|القيمة)[:\s]*\$?\s*([0-9.]+)',
    r '\$([0-9.]+)',
    r '([0-9.]+)\s*(?:USD|USDT|TRX)',
    r '(?:received|got)[:\s]*\$?\s*([0-9.]+)',
    r '\b(\d+(?:\.\d+)?)\s*(?:USD|USDT|TRX|دولار)\b'
]

# كلمات مفتاحية للبحث في الرسائل
KEYWORDS = [
    'code', 'reward', 'bonus', 'gift', 'كود', 'مكافأة', 'هدية', 'بريميوم',
    'code:', 'reward:', 'bonus:', 'gift:', 'كود:', 'مكافأة:', 'هدية:',
    'premium', 'vip', 'daily', 'drop'
]

# - تهيئة العميل -
client = TelegramClient('monitor_session', int(API_ID), API_HASH)

# - تخزين الأكواد المعالجة مؤقتاً لتجنب التكرار -
processed_codes = set()

# - دالة لاستخراج الأكواد والقيم من النص -
def extract_codes_and_values(text):
    """استخراج الأكواد والقيم من النص باستخدام الأنماط"""
    codes = []
    values = []
    original_text = text
    # تنظيف النص قليل
    text = re.sub(r '\s+', ' ', text)
    
    # البحث عن جميع الأنماط الممكنة للأكواد
    for pattern in CODE_PATTERNS:
        matches = re.findall(pattern, text)
        for match in matches:
            extracted_code = match if isinstance(match, str) else str(match)
            # التحقق من أن الكود لحاله (ليس جزء من كلمة أطول)
            full_pattern = r '\b' + re.escape(extracted_code) + r '\b'
            if (len(extracted_code) >= 6 and len(extracted_code) <= 30 and
                extracted_code not in processed_codes and
                re.search(full_pattern, original_text)): # استخدام النص الأصلي للتحقق
                codes.append(extracted_code) # الاحتفاظ بالأحرف الأصلية
                processed_codes.add(extracted_code) # تسجيل الكود كمعالج
                logger.info(f "[✅] كود بسيط مكتشف: {extracted_code}")

    # البحث عن القيم
    for pattern in VALUE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                value_text = match if isinstance(match, str) else str(match)
                value_float = float(value_text)
                if value_float > 0 and value_float < 100000: # قيمة معقولة
                    values.append(value_float)
                    logger.info(f "[💰] قيمة مكتشفة: ${value_float}")
            except (ValueError, IndexError):
                continue

    # تحديد أفضل كود وأفضل قيمة
    best_code = None
    best_value = 0.0

    # اختيار الكود الأطول أو الأكثر احتمالاً
    if codes:
        # ترتيب الأكواد حسب الطول والجودة
        codes.sort(key=lambda x: (-len(x), x))
        best_code = codes[0]

    if values:
        best_value = max(values)

    if best_code:
        logger.info(f "[🎯] النتيجة النهائية - الكود: {best_code}, القيمة: ${best_value}")

    return best_code, best_value

# - دالة لإرسال الكود للسيرفر -
async def send_code_to_server(code, channel_name, message_text, value=0.0):
    """إرسال الكود للسيرفر مع معلومات إضافية"""
    try:
        data = {
            "code": code,
            "source_channel": channel_name,
            "message_text": message_text,
            "value": value,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        # إرسال الطلب للسيرفر
        response = requests.post(
            f "{SERVER_URL}/api/codes/receive",
            json=data,
            timeout=10
        )
        logger.info(f "[📤] إرسال الكود {code} للسيرفر - الحالة: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f "[❌] خطأ في إرسال الكود للسيرفر: {e}")
        return False

# - دالة لإرسال الكود للقناة -
async def send_code_to_channel(code, channel_name, message_text, value=0.0):
    """إرسال الكود للقناة المحددة - الرسالة معدلة لتكون فقط الكود وسهولة النسخ"""
    try:
        # إنشاء رسالة بسيطة تحتوي فقط على الكود وعلامة لنسخه
        message = f "`{code}`"
        await client.send_message(entity=CHANNEL_TO_POST, message=message, parse_mode='Markdown')
        return True
    except Exception as e:
        logger.error(f "[❌] خطأ في إرسال الكود للقناة: {e}")
        return False

# - دالة لاستخراج النص من الصورة -
def extract_text_from_image(image_path):
    """استخراج النص من الصور باستخدام Tesseract OCR"""
    try:
        # فتح الصورة
        image = Image.open(image_path)
        
        # تحسين جودة الصورة للـ OCR
        # تحويل إلى رمادية
        image = image.convert('L')
        
        # تكبير الصورة إذا كانت صغيرة
        width, height = image.size
        if width < 600:
            scale = 600 / width
            image = image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
        
        # استخدام Tesseract لاستخراج النص
        # تأكد إن Tesseract مثبت ومساره صحيح
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # مثال على ويندوز
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        logger.error(f "[OCR] خطأ في استخراج النص من الصورة: {e}")
        return ""

# - دالة لاستخراج النص من الفيديو (محسّنة) -
def extract_text_from_video(video_path):
    """استخراج النص من مقاطع الفيديو - نسخة محسّنة"""
    try:
        logger.info(f "[🎥] بدء معالجة الفيديو: {video_path}")
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            logger.error(f "[🎥] لا يمكن فتح ملف الفيديو: {video_path}")
            return ""
        
        all_text = ""
        frame_count = 0
        processed_frames = 0
        
        # الحصول على معلومات الفيديو
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        logger.info(f "[🎥] إجمالي الإطارات: {total_frames}, FPS: {fps}")
        
        # معالجة كل 10 إطار للحصول على تغطية أفضل
        frame_interval = 10
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # معالجة كل frame_interval إطار
            if frame_count % frame_interval == 0:
                processed_frames += 1
                logger.debug(f "[🎥] معالجة الإطار {frame_count}/{total_frames}")
                
                try:
                    # تحسين جودة الإطار
                    height, width = frame.shape[:2]
                    
                    # تكبير الإطار إذا كان صغيراً
                    if width < 800:
                        scale = 800 / width
                        frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
                    
                    # تحويل إلى رمادية
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    
                    # تحسين التباين
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                    enhanced = clahe.apply(gray)
                    
                    # تحويل إلى صورة مؤقتة باستخدام tempfile بشكل آمن
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_img:
                        temp_frame_path = tmp_img.name
                        cv2.imwrite(temp_frame_path, enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    
                    # استخراج النص من الإطار
                    frame_text = extract_text_from_image(temp_frame_path)
                    if frame_text and len(frame_text.strip()) > 3: # فقط إذا كان النص كافياً
                        all_text += frame_text + " "
                        logger.debug(f "[🎥] نص من الإطار {frame_count}: {frame_text[:50]}...")
                    
                    # حذف الملف المؤقت فوراً بعد استخدامه
                    os.unlink(temp_frame_path)
                    
                except Exception as frame_error:
                    logger.error(f "[🎥] خطأ في معالجة الإطار {frame_count}: {frame_error}")
                    # التأكد من حذف الملف المؤقت حتى لو حصل خطأ
                    if 'temp_frame_path' in locals() and os.path.exists(temp_frame_path):
                        try:
                            os.unlink(temp_frame_path)
                        except OSError:
                            pass # تجاهل الأخطاء في الحذف
                    continue # تابع لمعالجة الإطار التالي
        
        cap.release()
        logger.info(f "[🎥] تم معالجة {processed_frames} إطار من إجمالي {total_frames} إطار")
        logger.info(f "[🎥] النص المستخرج من الفيديو طوله: {len(all_text)}")
        
        if len(all_text) > 0:
            logger.debug(f "[🎥] عينة من النص: {all_text[:200]}...")
        
        return all_text
        
    except Exception as e:
        logger.error(f "[OCR] خطأ في استخراج النص من الفيديو: {e}")
        return ""

# - دالة لتحميل الوسائط -
async def download_media(event):
    """تحميل الوسائط (صور/فيديو) من الرسالة"""
    try:
        if event.message.media:
            logger.info("[📥] بدء تحميل الوسائط...")
            # إنشاء مجلد مؤقت للتحميل
            temp_dir = tempfile.mkdtemp()
            # تحميل الملف
            file_path = await event.download_media(file=temp_dir)
            logger.info(f "[📥] تم تحميل الوسائط إلى: {file_path}")
            return file_path
    except Exception as e:
        logger.error(f "[📥] خطأ في تحميل الوسائط: {e}")
    return None

# - دالة لمعالجة الوسائط للبحث عن الأكواد -
async def process_media_for_codes(event):
    """معالجة الوسائط للبحث عن الأكواد"""
    try:
        file_path = await download_media(event)
        if not file_path:
            return None, 0.0
        
        text_from_media = ""
        
        # التحقق من نوع الملف
        if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp')):
            logger.info(f "[📸] معالجة صورة: {file_path}")
            # معالجة الصور
            text_from_media = extract_text_from_image(file_path)
            
        elif file_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            logger.info(f "[🎥] معالجة فيديو: {file_path}")
            # معالجة مقاطع الفيديو
            text_from_media = extract_text_from_video(file_path)
        
        # حذف الملف المؤقت بعد المعالجة
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                # إذا كان المجلد فارغ، احذفه كمان
                temp_dir = os.path.dirname(file_path)
                if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
            except OSError as e:
                logger.debug(f "[📥] لم أستطع حذف الملف المؤقت {file_path}: {e}")
        
        if text_from_media:
            logger.info(f "[📸] تم استخراج نص من الوسائط طوله: {len(text_from_media)}")
            return extract_codes_and_values(text_from_media)
        else:
            logger.info("[📸] لم يتم استخراج نص من الوسائط.")
            
    except Exception as e:
        logger.error(f "[📸] خطأ في معالجة الوسائط: {e}")
    
    return None, 0.0

# - مستمع الأحداث -
@client.on(events.NewMessage(chats=WATCHED_CHANNELS))
async def my_event_handler(event):
    """مستمع الأحداث الجديد للرسائل"""
    try:
        # الحصول على اسم القناة أو المجموعة بشكل آمن
        chat = await event.get_chat()
        # التحقق من أن الكائن فيه الخاصية المطلوبة
        if hasattr(chat, 'username') and chat.username:
            chat_identifier = chat.username
        elif hasattr(chat, 'title') and chat.title:
            chat_identifier = chat.title
        else:
            chat_identifier = f "ID: {chat.id}"
            
        logger.info(f "[🔍] رسالة محتملة من {chat_identifier}")
        
        # التحقق من أن الرسالة من قناة مراقبة (باستخدام المعرفات الرقمية أو الأسماء)
        # ملاحظة: WATCHED_CHANNELS لازم تحتوي على أسماء المستخدمين أو المعرفات الرقمية
        # هذا التحقق ممكن يحتاج تعديل حسب كيف تم تمرير أسماء القنوات لـ Telethon
        # للتبسيط، خلينا نعالج كل الرسائل من القنوات المراقبة
        
        # الحصول على نص الرسالة
        text = event.message.text or ""
        
        # التحقق من وجود كلمات مفتاحية أو نص قصير أو وسائط
        has_keywords = any(keyword in text.lower() for keyword in KEYWORDS)
        is_short_text = len(text) < 300 # زيادة الحد
        has_media = bool(event.message.media)
        
        if has_keywords or is_short_text or has_media:
            logger.info(f "[🔍] رسالة محتملة من {chat_identifier}")
            
            # معالجة الوسائط إذا وجدت
            media_code, media_value = None, 0.0
            if has_media:
                logger.info(f "[🎥] تم العثور على وسائط في الرسالة من {chat_identifier}")
                media_code, media_value = await process_media_for_codes(event)
                if media_code:
                    logger.info(f "[📸] كود مستخرج من الوسائط: {media_code} - القيمة: ${media_value}")
            
            # استخراج الكود من النص
            text_code, text_value = extract_codes_and_values(text)
            
            # تحديد الكود والقيمة النهائية
            final_code = media_code or text_code
            final_value = max(media_value, text_value)
            
            # إذا تم العثور على كود، نرسله
            if final_code:
                logger.info(f "[✅] كود مكتشف: {final_code} - القيمة: ${final_value} - من: {chat_identifier}")
                
                # إنشاء نص مركب للرسالة
                combined_text = text
                if media_code:
                    combined_text += f " [محتوى الوسائط: {media_code}]"
                
                # إرسال الكود للسيرفر
                success_server = await send_code_to_server(final_code, chat_identifier, combined_text, final_value)
                if success_server:
                    logger.info(f "[🚀] تم إرسال الكود {final_code} للسيرفر")
                else:
                    logger.error(f "[❌] فشل إرسال الكود {final_code} للسيرفر")
                
                # إرسال الكود للقناة (الرسالة معدلة)
                success_channel = await send_code_to_channel(final_code, chat_identifier, combined_text, final_value)
                if success_channel:
                    logger.info(f "[📤] تم إرسال الكود {final_code} للقناة")
                else:
                    logger.error(f "[❌] فشل إرسال الكود {final_code} للقناة")
            else:
                logger.debug(f "[🔍] لم يتم العثور على أكواد في الرسالة من {chat_identifier}")
        else:
            logger.debug(f "[🔍] الرسالة من {chat_identifier} لا تحتوي على كلمات مفتاحية أو نص قصير أو وسائط.")
            
    except Exception as e:
        logger.error(f "[💥] خطأ غير متوقع في معالجة الرسالة: {e}")
        # طباعة التتبع الكامل للخطأ علشان نفهم وين حصل الخطأ
        import traceback
        logger.debug(traceback.format_exc())

# - الدالة الرئيسية -
async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # بدء الجلسة
    await client.start()
    logger.info("🤖 بوت مراقبة القنوات يعمل...")
    
    # تشغيل البوت إلى الأبد
    await client.run_until_disconnected()

# - تشغيل البوت -
if __name__ == '__main__':
    # تشغيل الحلقة الرئيسية
    asyncio.run(main())
