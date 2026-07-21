import os
import json
import tempfile
import google.generativeai as genai
from typing import Dict, Any, Optional

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Thiếu GEMINI_API_KEY!")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

model = genai.GenerativeModel(
    model_name=MODEL_NAME,
    generation_config={
        "temperature": 0.2,
        "max_output_tokens": 900,
        "response_mime_type": "application/json",
    }
)

SYSTEM_PROMPT = """Bạn là trợ lý tài chính thông minh cho người Việt Nam, chuyên quản lý thu chi cá nhân qua Telegram.

NHIỆM VỤ:
Phân tích tin nhắn (text / thoại / ảnh hóa đơn) và trả về JSON hành động phù hợp.

CÁC ACTION HỖ TRỢ:
- add_transaction: Thêm thu/chi (params: type, amount, category, description, wallet_name?)
- update_transaction: Sửa giao dịch (params: tx_id, amount?, category?, description?, wallet_name?)
- delete_transaction: Xóa giao dịch (params: tx_id)
- get_balance: Xem số dư tổng hoặc theo ví (params: wallet_name?)
- get_list: Xem danh sách giao dịch
- get_report: Báo cáo thu chi
- get_chart: Biểu đồ (params: chart_type = "category" | "daily" | "income_expense")
- get_prediction: Dự đoán chi tiêu tháng
- create_wallet: Tạo ví mới (params: name, type?)  type = cash|bank|momo|zalopay|credit|other
- list_wallets: Xem danh sách ví + số dư
- transfer: Chuyển tiền giữa 2 ví (params: from_wallet, to_wallet, amount, description?)
- set_remind: Bật/tắt nhắc nhở
- help: Hướng dẫn
- chat: Trả lời câu hỏi chung

QUY TẮC PARSE SỐ TIỀN:
- "50k", "50K", "50 nghìn" → 50000
- "1.5tr", "1tr5", "1.5 triệu" → 1500000
- "2tr", "2 triệu" → 2000000
- Luôn trả về số thực (float) đơn vị VNĐ.

DANH MỤC phổ biến:
Thu: Lương, Thưởng, Đầu tư, Kinh doanh, Quà tặng, Khác
Chi: Ăn uống, Di chuyển, Nhà cửa, Hóa đơn, Mua sắm, Giải trí, Sức khỏe, Giáo dục, Du lịch, Khác

VÍ MẶC ĐỊNH: "Tiền mặt".

QUY TẮC VIẾT TẮT VÍ / NGÂN HÀNG (rất quan trọng - phải mở rộng viết tắt thành tên đầy đủ):
- VT, VTB, Viettin, Viettinbank, Vietin → "VietinBank"
- VCB, Vietcom, Vietcombank → "Vietcombank"
- TCB, Techcom, Techcombank → "Techcombank"
- MB, MBB, MBBank → "MB Bank"
- ACB → "ACB"
- BIDV → "BIDV"
- VPB, VPBank → "VPBank"
- TPB, TPBank → "TPBank"
- STB, Sacombank → "Sacombank"
- AGR, Agribank → "Agribank"
- MoMo, momo, Momo → "MoMo"
- ZaloPay, zalopay, Zalo → "ZaloPay"
- ShopeePay, Shopee → "ShopeePay"
- ViettelPay, Viettel → "ViettelPay"
- TM, Tien mat, Cash → "Tiền mặt"

Khi user nói viết tắt, LUÔN dùng tên đầy đủ ở trên trong params (wallet_name, from_wallet, to_wallet, name).

ĐỊNH DẠNG BẮT BUỘC (chỉ JSON thuần):
{
  "action": "tên_action",
  "params": { ... },
  "reply": "Tin nhắn thân thiện bằng tiếng Việt có emoji (để rỗng nếu cần lấy data từ DB)"
}

VÍ DỤ:

User: "chi 45k cafe bằng MoMo"
→ {"action":"add_transaction","params":{"type":"expense","amount":45000,"category":"Ăn uống","description":"Cafe","wallet_name":"MoMo"},"reply":"✅ Đã ghi nhận chi **45.000₫** cho *Cafe* từ ví MoMo"}

User: "tạo ví VT" hoặc "tạo ví Viettinbank"
→ {"action":"create_wallet","params":{"name":"VietinBank","type":"bank"},"reply":"🆕 Đã tạo ví **VietinBank** thành công!"}

User: "tạo ví VCB"
→ {"action":"create_wallet","params":{"name":"Vietcombank","type":"bank"},"reply":"🆕 Đã tạo ví **Vietcombank** thành công!"}

User: "chuyển 500k từ tiền mặt sang VT"
→ {"action":"transfer","params":{"from_wallet":"Tiền mặt","to_wallet":"VietinBank","amount":500000},"reply":""}

User: "số dư ví TCB"
→ {"action":"get_balance","params":{"wallet_name":"Techcombank"},"reply":""}

User: "danh sách ví" / "các ví của tôi"
→ {"action":"list_wallets","params":{},"reply":""}

User: "sửa #12 thành 60k"
→ {"action":"update_transaction","params":{"tx_id":12,"amount":60000},"reply":""}
"""


def _parse_json_response(content: str) -> Dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith("json"):
                content = content[4:]
    content = content.strip()
    try:
        result = json.loads(content)
        if "action" not in result:
            result = {
                "action": "chat",
                "params": {},
                "reply": "Xin lỗi, mình chưa hiểu rõ. Bạn thử nói lại nhé!"
            }
        return result
    except Exception:
        return {
            "action": "chat",
            "params": {},
            "reply": "Xin lỗi, mình chưa hiểu rõ. Bạn thử nói: 'chi 50k ăn trưa' hoặc 'số dư' nhé!"
        }


async def process_message(user_message: str, user_id: int) -> Dict[str, Any]:
    try:
        prompt = f"{SYSTEM_PROMPT}\n\nTin nhắn của người dùng (user_id={user_id}):\n{user_message}"
        response = model.generate_content(prompt)
        return _parse_json_response(response.text)
    except Exception as e:
        print(f"[Gemini Error] {e}")
        return {
            "action": "chat",
            "params": {},
            "reply": f"⚠️ Lỗi AI: {str(e)[:120]}. Thử lại sau nhé!"
        }


async def process_voice(audio_bytes: bytes, user_id: int, mime_type: str = "audio/ogg") -> Dict[str, Any]:
    tmp_path = None
    uploaded_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        uploaded_file = genai.upload_file(path=tmp_path, mime_type=mime_type)

        prompt = f"""{SYSTEM_PROMPT}

Đây là tin nhắn thoại tiếng Việt từ user_id={user_id}.
1. Nghe và chuyển thành văn bản tiếng Việt chính xác.
2. Phân tích như tin nhắn thu chi thông thường.
3. Trả về ĐÚNG JSON action (chỉ JSON thuần).
"""
        response = model.generate_content([prompt, uploaded_file])
        return _parse_json_response(response.text)
    except Exception as e:
        print(f"[Gemini Voice Error] {e}")
        return {
            "action": "chat",
            "params": {},
            "reply": f"⚠️ Không nhận diện được tin nhắn thoại: {str(e)[:100]}"
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
                pass


async def process_image(image_bytes: bytes, user_id: int, mime_type: str = "image/jpeg") -> Dict[str, Any]:
    """
    OCR hóa đơn / ảnh → trích xuất số tiền, cửa hàng, gợi ý danh mục → add_transaction
    """
    tmp_path = None
    uploaded_file = None
    try:
        suffix = ".jpg" if "jpeg" in mime_type or "jpg" in mime_type else ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        uploaded_file = genai.upload_file(path=tmp_path, mime_type=mime_type)

        prompt = f"""{SYSTEM_PROMPT}

Đây là ảnh hóa đơn / biên lai / screenshot giao dịch từ user_id={user_id}.

Hãy thực hiện:
1. Đọc kỹ ảnh (OCR) để lấy:
   - Tổng số tiền thanh toán (ưu tiên số lớn nhất / "Tổng cộng" / "Total" / "Thành tiền")
   - Tên cửa hàng / merchant (nếu có)
   - Ngày tháng (nếu có)
2. Đoán danh mục phù hợp (Ăn uống, Mua sắm, Di chuyển, Hóa đơn...)
3. Trả về action "add_transaction" với type="expense".

Ví dụ JSON:
{{
  "action": "add_transaction",
  "params": {{
    "type": "expense",
    "amount": 145000,
    "category": "Ăn uống",
    "description": "Highland Coffee"
  }},
  "reply": "🧾 Đã nhận diện hóa đơn **145.000₫** tại *Highland Coffee* (Ăn uống). Đã ghi nhận!"
}}

Nếu không đọc được số tiền rõ ràng:
{{
  "action": "chat",
  "params": {{}},
  "reply": "Mình không đọc rõ số tiền trên ảnh. Bạn có thể nhắn text giúp mình không?"
}}
"""
        response = model.generate_content([prompt, uploaded_file])
        return _parse_json_response(response.text)
    except Exception as e:
        print(f"[Gemini Image Error] {e}")
        return {
            "action": "chat",
            "params": {},
            "reply": f"⚠️ Không đọc được ảnh hóa đơn: {str(e)[:100]}"
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
                pass


def format_money(amount: float) -> str:
    if abs(amount) >= 1_000_000:
        return f"{amount/1_000_000:,.2f} triệu".replace(".00", "") + "₫"
    elif abs(amount) >= 1_000:
        return f"{amount/1_000:,.0f}k₫"
    else:
        return f"{amount:,.0f}₫"


def format_balance(data: Dict, wallet_name: str = None) -> str:
    income = format_money(data["income"])
    expense = format_money(data["expense"])
    balance = format_money(data["balance"])
    emoji = "🟢" if data["balance"] >= 0 else "🔴"
    title = f"💰 **SỐ DƯ {('VÍ ' + wallet_name.upper()) if wallet_name else 'TỔNG'}**"
    return (
        f"{title}\n\n"
        f"📥 Tổng thu: **{income}**\n"
        f"📤 Tổng chi: **{expense}**\n"
        f"{emoji} Còn lại: **{balance}**"
    )


def format_list(txs: list) -> str:
    if not txs:
        return "📭 Chưa có giao dịch nào."

    lines = ["📋 **GIAO DỊCH GẦN NHẤT**\n"]
    for tx in txs:
        icon = "📥" if tx["type"] == "income" else "📤"
        amount = format_money(tx["amount"])
        created = tx["created_at"]
        if hasattr(created, "strftime"):
            date_str = created.strftime("%d/%m %H:%M")
        else:
            date_str = str(created)[:16].replace("T", " ")
        desc = tx["description"] or tx["category"]
        wallet = tx.get("wallet_name") or "Tiền mặt"
        lines.append(
            f"{icon} `#{tx['id']}` {amount} — {desc}\n"
            f"   └ {tx['category']} • {wallet} • {date_str}"
        )
    return "\n".join(lines)


def format_report(data: Dict) -> str:
    days = data["days"]
    income = format_money(data["income"])
    expense = format_money(data["expense"])
    balance = format_money(data["balance"])
    emoji = "🟢" if data["balance"] >= 0 else "🔴"

    lines = [
        f"📊 **BÁO CÁO {days} NGÀY GẦN NHẤT**\n",
        f"📥 Thu: **{income}**",
        f"📤 Chi: **{expense}**",
        f"{emoji} Chênh lệch: **{balance}**\n"
    ]

    if data["by_category"]:
        lines.append("🏷️ **Chi theo danh mục:**")
        for item in data["by_category"]:
            pct = (item["total"] / data["expense"] * 100) if data["expense"] > 0 else 0
            lines.append(
                f"• {item['category']}: {format_money(item['total'])} ({pct:.0f}%)"
            )
    else:
        lines.append("Chưa có chi tiêu nào trong khoảng thời gian này.")

    return "\n".join(lines)


def format_prediction(data: Dict) -> str:
    return (
        f"🔮 **DỰ ĐOÁN CHI TIÊU THÁNG NÀY**\n\n"
        f"📅 Đã qua: **{data['days_passed']}/{data['days_in_month']}** ngày\n"
        f"📅 Còn lại: **{data['remaining_days']}** ngày\n\n"
        f"📤 Chi tiêu đến nay: **{format_money(data['expense_so_far'])}**\n"
        f"📥 Thu nhập đến nay: **{format_money(data['income_so_far'])}**\n"
        f"💵 Số dư tạm: **{format_money(data['balance_so_far'])}**\n\n"
        f"📈 Trung bình/ngày: **{format_money(data['avg_daily'])}**\n"
        f"🎯 Dự kiến chi thêm: **{format_money(data['predicted_remaining'])}**\n"
        f"🏁 Tổng chi dự kiến cả tháng: **{format_money(data['predicted_total'])}**\n\n"
        f"💡 *Dựa trên trung bình chi tiêu {data['days_passed']} ngày qua.*"
    )


def format_daily_reminder(data: Dict) -> str:
    return (
        f"🌙 **NHẮC NHỞ CUỐI NGÀY**\n\n"
        f"Hôm nay bạn đã chi: **{format_money(data['expense_today'])}**\n\n"
        f"📊 Tháng này:\n"
        f"• Đã chi: **{format_money(data['expense_so_far'])}** ({data['days_passed']} ngày)\n"
        f"• Trung bình/ngày: **{format_money(data['avg_daily'])}**\n"
        f"• Dự kiến còn chi: **{format_money(data['predicted_remaining'])}**\n"
        f"• Tổng dự kiến: **{format_money(data['predicted_total'])}**\n\n"
        f"Nhớ ghi lại mọi khoản chi để theo dõi chính xác nhé! 💪"
    )


def format_wallets(wallets: list) -> str:
    if not wallets:
        return "📭 Bạn chưa có ví nào."

    lines = ["👛 **DANH SÁCH VÍ CỦA BẠN**\n"]
    total = 0.0
    for w in wallets:
        bal = float(w["balance"])
        total += bal
        emoji = "⭐" if w["is_default"] else "•"
        icon = {
            "cash": "💵", "bank": "🏦", "momo": "📱",
            "zalopay": "💜", "credit": "💳"
        }.get(w["type"], "👛")
        lines.append(f"{emoji} {icon} **{w['name']}**: {format_money(bal)}")

    lines.append(f"\n💰 **Tổng cộng tất cả ví: {format_money(total)}**")
    return "\n".join(lines)
