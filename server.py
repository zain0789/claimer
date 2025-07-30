# server.py
from flask import Flask, request, jsonify
from database import db, User, GiftCode, Code # <-- إضافة Code
from datetime import datetime
import os

app = Flask(__name__)
# استخدام قاعدة البيانات من مجلد instance أو Render Postgres
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Render (Postgres) - SQLAlchemy needs the URL to start with postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local development
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'stake_system.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Ensure the instance folder exists for SQLite
if not database_url: # Only for local SQLite
    os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)

with app.app_context():
    db.create_all()

@app.route('/api/validate-token', methods=['POST'])
def validate_token():
    try:
        data = request.json
        token = data.get('token')
        if not token:
            return jsonify({"valid": False, "message": "رمز غير متوفر"})

        user = User.query.filter_by(script_token=token).first()
        if user and user.is_active and user.subscription_end > datetime.utcnow():
            return jsonify({"valid": True, "message": "رمز صحيح واشتراك ساري"})
        else:
            return jsonify({"valid": False, "message": "رمز غير صالح أو اشتراك غير مفعل"})
    except Exception as e:
        return jsonify({"valid": False, "message": str(e)}), 500

# ***** إضافة دالة بتستقبل الكود من المستمع *****
@app.route('/api/codes/receive', methods=['POST'])
def receive_code():
    try:
        data = request.json
        # التحقق من البيانات الأساسية
        code_text = data.get('code')
        if not code_text:
            return jsonify({"status": "error", "message": "الكود مطلوب"}), 400

        # التحقق من أن الكود مش موجود من قبل (علشان ما يتكررش)
        existing_code = Code.query.filter_by(code=code_text).first()
        if existing_code:
             # إذا موجود، نرجع رسالة نجاح بس علشان ما يضلش المستمع يعيد إرساله
             return jsonify({"status": "success", "message": "الكود موجود مسبقاً"}), 200

        # إنشاء كائن كود جديد
        new_code = Code(
            code=code_text,
            value=data.get('value', 0.0),
            source_channel=data.get('source_channel'),
            message_text=data.get('message_text'),
            received_at=datetime.fromisoformat(data.get('timestamp').replace('Z', '+00:00')) if data.get('timestamp') else datetime.utcnow()
        )
        db.session.add(new_code)
        db.session.commit()
        print(f"[📥] تم استقبال كود جديد: {code_text} من {data.get('source_channel', 'غير محدد')}") # تسجيل في الكونسول
        return jsonify({"status": "success", "message": "تم استقبال الكود"}), 200
    except Exception as e:
        db.session.rollback()
        print(f"[❌] خطأ في استقبال الكود: {e}") # تسجيل في الكونسول
        return jsonify({"status": "error", "message": str(e)}), 500
# ************************************************

@app.route('/api/codes/pending', methods=['GET'])
def get_pending_codes():
    try:
        script_token = request.headers.get('Script-Token')
        if not script_token:
            return jsonify({"status": "error", "message": "رمز السكربت مطلوب"}), 401

        user = User.query.filter_by(script_token=script_token, is_active=True).first()
        if not user or user.subscription_end < datetime.utcnow():
            return jsonify({"status": "error", "message": "اشتراك غير صالح"}), 401

        # ***** تعديل: جلب أول كود مش مستخدم *****
        pending_code = Code.query.filter_by(is_used=False).order_by(Code.received_at.asc()).first()
        if pending_code:
            # تقديم الكود للسكربت
            return jsonify([{
                "id": pending_code.id,
                "code": pending_code.code,
                "value": pending_code.value or 0.0,
                "timestamp": pending_code.received_at.isoformat()
            }])
        else:
            # إذا ما فيش أكواد، نبعت array فاضي
            return jsonify([])
        # *******************************
    except Exception as e:
        print(f"[❌] خطأ في جلب الكود المعلق: {e}") # تسجيل في الكونسول
        return jsonify({"status": "error", "message": str(e)}), 500

# ***** إضافة دالة علشان السكربت يبلغ إن الكود اشتُغل *****
@app.route('/api/codes/<int:code_id>/claim', methods=['POST'])
def claim_code(code_id):
    try:
        script_token = request.headers.get('Script-Token')
        if not script_token:
            return jsonify({"status": "error", "message": "رمز السكربت مطلوب"}), 401

        user = User.query.filter_by(script_token=script_token, is_active=True).first()
        if not user or user.subscription_end < datetime.utcnow():
            return jsonify({"status": "error", "message": "اشتراك غير صالح"}), 401

        # جلب الكود
        code_to_claim = Code.query.filter_by(id=code_id).first()
        if not code_to_claim:
            return jsonify({"status": "error", "message": "الكود مش موجود"}), 404

        # تحديث الكود إنه اشتُغل
        code_to_claim.is_used = True
        code_to_claim.used_by_script_token = script_token
        code_to_claim.used_at = datetime.utcnow()

        db.session.commit()
        print(f"[✅] تم استخدام الكود: {code_to_claim.code} بواسطة {user.username or user.user_id} ({script_token})") # تسجيل في الكونسول
        return jsonify({"status": "success", "message": "تم تسجيل استخدام الكود"}), 200

    except Exception as e:
        db.session.rollback()
        print(f"[❌] خطأ في تسجيل استخدام الكود: {e}") # تسجيل في الكونسول
        return jsonify({"status": "error", "message": str(e)}), 500
# ******************************************************

# Health check endpoint for Render
@app.route('/')
def home():
    return "🚀 السيرفر شغال!", 200

if __name__ == '__main__':
    # Don't run in debug mode on Render
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug_mode)
