import os
import json
import tempfile
from typing import Dict, Any, Optional
from openai import OpenAI, AsyncOpenAI

# ==================== CẤU HÌNH ====================
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()  # groq | gemini
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Model mặc định
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_WHISPER_MODEL = "whisper-large-v3"

# Client
client = None

if AI_PROVIDER == "groq":
    if not GROQ_API_KEY:
        raise ValueError("Thiếu GROQ_API_KEY! Lấy key miễn phí tại https://console.groq.com/keys")
    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )
    print(f"[AI] Đang dùng Groq - model: {GROQ_MODEL}")
else:
    # Fallback Gemini (nếu user muốn)
    import google.generativeai as genai
    if not GEMINI_API_KEY:
        raise ValueError("Thiếu GEMINI_API_KEY!")
    genai.configure(api_key=GEMINI_API_KEY)
    print("[AI] Đang dùng Gemini")


SYSTEM_PROMPT = """Bạn là trợ lý tài chính thông minh cho người Việt Nam, chuyên quản lý thu chi cá nhân qua Telegram.

NHIỆM VỤ:
Phân tích tin nhắn và trả về JSON hành động phù hợp.

CÁC ACTION HỖ TRỢ:
- add_transaction: Thêm thu/chi (params: type, amount, category, description, wallet_name?)
- update_transaction: Sửa giao dịch (params: tx_id, amount?, category?, description?, wallet_name?)
- delete_transaction: Xóa giao dịch (params: tx_id)
- get_balance: Xem số dư tổng hoặc theo ví (params: wallet_name?)
- get_list: Xem danh sách giao dịch
- get_report: Báo cáo thu chi
- get_chart: Biểu đồ (params: chart_type = "category" | "daily" | "income_expense")
- get_prediction: Dự đoán chi tiêu tháng
- create_wallet: Tạo ví mới (params: name, type?)
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

QUY TẮC VIẾT TẮT VÍ (phải mở rộng thành tên đầy đủ):
- VT, VTB, Viettin, Vietin → "VietinBank"
- VCB, Vietcom → "Vietcombank"
- TCB, Techcom → "Techcombank"
- MB, MBB → "MB Bank"
- ACB, BIDV, VPB, TPB, STB, AGR...
- MoMo, ZaloPay, ShopeePay, ViettelPay
- TM, Tiền mặt → "Tiền mặt"

ĐỊNH DẠNG BẮT BUỘC (chỉ trả JSON thuần, không markdown):
{
  "action": "tên_action",
  "params": { ... },
  "reply": "Tin nhắn thân thiện bằng tiếng Việt có emoji"
}

VÍ DỤ:
User: "chi 45k cafe bằng MoMo"
→ {"action":"add_transaction","params":{"type":"expense","amount":45000,"category":"Ăn uống","description":"Cafe","wallet_name":"MoMo"},"reply":"✅ Đã ghi nhận chi **45.000₫** cho *Cafe* từ ví MoMo"}

User: "tạo ví VT"
→ {"action":"create_wallet","params":{"name":"VietinBank","type":"bank"},"reply":"🆕 Đã tạo ví **VietinBank** thành công!"}

User: "chuyển 500k từ tiền mặt sang VCB"
→ {"action":"transfer","params":{"from_wallet":"Tiền mặt","to_wallet":"Vietcombank","amount":500000},"reply":""}
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
            "reply": "Xin lỗi, mình chưa hiểu rõ. Bạn thử: 'chi 50k ăn trưa' hoặc 'số dư' nhé!"
        }


async def process_message(user_message: str, user_id: int) -> Dict[str, Any]:
    """Xử lý tin nhắn text"""
    try:
        if AI_PROVIDER == "groq":
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"user_id={user_id}\n{user_message}"}
                ],
                temperature=0.2,
                max_tokens=800,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return _parse_json_response(content)
        else:
            # Gemini fallback
            import google.generativeai as genai
            model = genai.GenerativeModel(
                model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                generation_config={"temperature": 0.2, "response_mime_type": "application/json"}
            )
            prompt = f"{SYSTEM_PROMPT}\n\nTin nhắn (user_id={user_id}):\n{user_message}"
            response = model.generate_content(prompt)
            return _parse_json_response(response.text)
    except Exception as e:
        print(f"[AI Error] {e}")
        return {
            "action": "chat",
            "params": {},
            "reply": f"⚠️ Lỗi AI: {str(e)[:120]}. Thử lại sau nhé!"
        }


async def process_voice(audio_bytes: bytes, user_id: int, mime_type: str = "audio/ogg") -> Dict[str, Any]:
    """
    Tin nhắn thoại:
    - Groq: dùng Whisper miễn phí chuyển thành text → xử lý như tin nhắn thường
    - Gemini: multimodal (nếu còn dùng)
    """
    try:
        if AI_PROVIDER == "groq":
            # 1. Transcribe bằng Whisper của Groq
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        model=GROQ_WHISPER_MODEL,
                        file=audio_file,
                        language="vi"  # ưu tiên tiếng Việt
                    )
                text = transcription.text.strip()
                print(f"[Whisper] Transcript: {text}")

                if not text:
                    return {
                        "action": "chat",
                        "params": {},
                        "reply": "Mình không nghe rõ tin nhắn thoại. Bạn thử nói lại rõ hơn nhé!"
                    }

                # 2. Đưa text vào AI xử lý bình thường
                result = await process_message(text, user_id)
                # Thêm thông tin transcript vào reply nếu là chat
                if result.get("action") == "chat" and text:
                    result["reply"] = f"🎧 Mình nghe: \"{text}\"\n\n{result.get('reply', '')}"
                return result
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        else:
            # Gemini multimodal (giữ lại nếu user dùng Gemini)
            import google.generativeai as genai
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            try:
                uploaded = genai.upload_file(path=tmp_path, mime_type=mime_type)
                model = genai.GenerativeModel(
                    model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    generation_config={"temperature": 0.2, "response_mime_type": "application/json"}
                )
                prompt = f"{SYSTEM_PROMPT}\n\nĐây là tin nhắn thoại tiếng Việt từ user_id={user_id}. Hãy nghe, chuyển thành text rồi phân tích action."
                response = model.generate_content([prompt, uploaded])
                return _parse_json_response(response.text)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    except Exception as e:
        print(f"[Voice Error] {e}")
        return {
            "action": "chat",
            "params": {},
            "reply": f"⚠️ Không nhận diện được tin nhắn thoại: {str(e)[:100]}"
        }


async def process_image(image_bytes: bytes, user_id: int, mime_type: str = "image/jpeg") -> Dict[str, Any]:
    """OCR hóa đơn – hiện chỉ hỗ trợ tốt với Gemini. Groq free chưa có vision."""
    if AI_PROVIDER == "groq":
        return {
            "action": "chat",
            "params": {},
            "reply": "📷 Hiện tại đang dùng **Groq** (miễn phí) nên chưa hỗ trợ đọc ảnh hóa đơn.\n\nBạn hãy nhắn text giúp mình, ví dụ:\n`chi 145k Highland Coffee`"
        }

    # Gemini vision
    try:
        import google.generativeai as genai
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            uploaded = genai.upload_file(path=tmp_path, mime_type=mime_type)
            model = genai.GenerativeModel(
                model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                generation_config={"temperature": 0.2, "response_mime_type": "application/json"}
            )
            prompt = f"""{SYSTEM_PROMPT}

Đây là ảnh hóa đơn từ user_id={user_id}.
Hãy OCR lấy số tiền + tên cửa hàng + gợi ý danh mục, rồi trả action add_transaction.
"""
            response = model.generate_content([prompt, uploaded])
            return _parse_json_response(response.text)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    except Exception as e:
        print(f"[Image Error] {e}")
        return {
            "action": "chat",
            "params": {},
            "reply": f"⚠️ Không đọc được ảnh: {str(e)[:100]}"
        }


# ==================== FORMAT ====================
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
            lines.append(f"• {item['category']}: {format_money(item['total'])} ({pct:.0f}%)")
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
        icon = {"cash": "💵", "bank": "🏦", "momo": "📱", "zalopay": "💜", "credit": "💳"}.get(w["type"], "👛")
        lines.append(f"{emoji} {icon} **{w['name']}**: {format_money(bal)}")
    lines.append(f"\n💰 **Tổng cộng tất cả ví: {format_money(total)}**")
    return "\n".join(lines)
