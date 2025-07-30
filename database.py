# database.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False) # معرف تليغرام
    username = db.Column(db.String(100)) # اسم المستخدم المخصص
    subscription_end = db.Column(db.DateTime, default=datetime.utcnow)
    script_token = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # إضافة تاريخ التسجيل

class GiftCode(db.Model):
    __tablename__ = 'gift_code'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    value_usd = db.Column(db.Float, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    used_by_user_id = db.Column(db.String(50), db.ForeignKey('user.user_id'), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    issued_by = db.Column(db.String(50), nullable=False) # معرف الدعم
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)

# ***** إضافة جدول جديد للأكواد من المستمع *****
class Code(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False) # نص الكود
    value = db.Column(db.Float, nullable=True) # القيمة (اختياري)
    source_channel = db.Column(db.String(100), nullable=True) # القناة المصدر
    is_used = db.Column(db.Boolean, default=False) # هل اشتُغل؟
    used_by_script_token = db.Column(db.String(50), db.ForeignKey('user.script_token'), nullable=True) # الرمز اللي استخدمه
    used_at = db.Column(db.DateTime, nullable=True) # وقت الاستخدام
    received_at = db.Column(db.DateTime, default=datetime.utcnow) # وقت الاستلام من المستمع
    message_text = db.Column(db.Text, nullable=True) # نص الرسالة الأصلي (اختياري)
# ***********************************
