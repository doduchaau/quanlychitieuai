# 🤖 Bot Quản Lý Thu Chi AI (Gemini + Neon Postgres)

Bot Telegram thông minh quản lý thu chi cá nhân bằng **tiếng Việt tự nhiên** + hỗ trợ nhiều ví + OCR hóa đơn + tin nhắn thoại.

**Công nghệ:**
- AI: **Google Gemini** (miễn phí)
- Database: **Neon Postgres** (miễn phí, dữ liệu vĩnh viễn)
- Host: **Render.com** Free + **UptimeRobot** giữ bot sống
- Biểu đồ: Matplotlib
- Nhắc nhở cuối ngày tự động

---

## ✨ Tính năng

| Tính năng | Cách dùng |
|-----------|-----------|
| Thêm thu/chi | `chi 45k cafe` · `thu 8tr lương` |
| **Sửa giao dịch** | `sửa #12 thành 60k` |
| **Xóa giao dịch** | `xóa #5` |
| Số dư / Báo cáo | `số dư` · `báo cáo 7 ngày` |
| **Dự đoán chi tiêu** | `dự đoán` |
| **Biểu đồ** | `biểu đồ danh mục` · `biểu đồ thu chi` |
| **Nhắc nhở cuối ngày** | Tự động lúc 21:00 |
| **Nhiều ví / tài khoản** | `tạo ví MoMo` · `chuyển 500k từ tiền mặt sang MoMo` |
| **OCR hóa đơn** | Gửi ảnh hóa đơn → Bot tự đọc số tiền |
| **Tin nhắn thoại** | Gửi voice → Bot tự nghe & ghi nhận |
| Hỏi AI tài chính | `làm sao để tiết kiệm?` |

---

# 🚀 HƯỚNG DẪN DEPLOY CHI TIẾT (TỪNG BƯỚC)

Làm theo đúng thứ tự dưới đây. Tổng thời gian khoảng **20-30 phút**.

---

## BƯỚC 0: Chuẩn bị tài khoản (miễn phí hết)

Bạn cần tạo 6 tài khoản sau (nếu chưa có):

| # | Dịch vụ | Link | Mục đích |
|---|---------|------|----------|
| 1 | Telegram | Đã có sẵn | Chat với bot |
| 2 | BotFather | https://t.me/BotFather | Tạo bot + lấy Token |
| 3 | Google AI Studio | https://aistudio.google.com/apikey | Lấy Gemini API Key |
| 4 | Neon.tech | https://console.neon.tech | Database Postgres miễn phí |
| 5 | GitHub | https://github.com | Lưu source code |
| 6 | Render.com | https://render.com | Host bot (đăng ký bằng GitHub) |
| 7 | UptimeRobot | https://uptimerobot.com | Ping giữ bot không bị sleep |

---

## BƯỚC 1: Tạo Bot Telegram

1. Mở Telegram, tìm **@BotFather**
2. Gửi lệnh: `/newbot`
3. Đặt tên bot (ví dụ: `Quản Lý Thu Chi AI`)
4. Đặt username bot (phải kết thúc bằng `bot`, ví dụ: `my_thuchi_ai_bot`)
5. BotFather sẽ trả về **Token** dạng:
   ```
   7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   ```
6. **Copy và lưu token này** cẩn thận (sẽ dùng ở Bước 5)

> Gợi ý: Gửi `/setdescription` và `/setabouttext` để bot đẹp hơn.

---

## BƯỚC 2: Lấy Gemini API Key (miễn phí)

1. Vào https://aistudio.google.com/apikey
2. Đăng nhập bằng tài khoản Google
3. Bấm **Create API Key** → chọn project hoặc tạo mới
4. Copy API Key (dạng `AIzaSy...`)
5. **Lưu lại**

> Lưu ý: Gemini free tier đủ dùng cá nhân. Nếu hết quota thì đợi sang ngày mới.

---

## BƯỚC 3: Tạo Database Neon (Postgres miễn phí)

1. Vào https://console.neon.tech → đăng ký/đăng nhập (dùng GitHub hoặc Google)
2. Bấm **Create a project**
   - Project name: `thu-chi-bot` (hoặc tên bất kỳ)
   - Region: chọn **Singapore** hoặc **Asia** gần nhất
   - Postgres version: để mặc định
3. Sau khi tạo xong, vào trang **Dashboard** của project
4. Tìm phần **Connection string**
5. Chọn **URI** (không phải Pooled connection nếu không cần)
6. Copy chuỗi dạng:
   ```
   postgresql://neondb_owner:npg_xxxxxxxxxxxx@ep-xxxx-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
7. **Lưu lại** (đây là `DATABASE_URL`)

> Quan trọng: Chuỗi phải có `?sslmode=require` ở cuối.

---

## BƯỚC 4: Đẩy code lên GitHub

### Cách 1: Dùng giao diện GitHub (dễ nhất cho người mới)

1. Vào https://github.com → **New repository**
2. Đặt tên: `telegram-thu-chi-bot`
3. Chọn **Public**
4. **Không** tích "Add a README"
5. Bấm **Create repository**
6. Ở trang repo vừa tạo, bấm **uploading an existing file**
7. Kéo thả **toàn bộ file** trong thư mục `telegram-thu-chi-bot` vào
8. Viết commit message: `Initial commit`
9. Bấm **Commit changes**

### Cách 2: Dùng dòng lệnh (nếu đã cài Git)

```bash
cd telegram-thu-chi-bot
git init
git add .
git commit -m "Telegram Thu Chi Bot - Gemini + Neon + Wallets + OCR"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/telegram-thu-chi-bot.git
git push -u origin main
```

---

## BƯỚC 5: Deploy lên Render.com

1. Vào https://dashboard.render.com
2. Đăng ký / Đăng nhập bằng **GitHub**
3. Bấm **New +** → chọn **Web Service**
4. Tìm và chọn repository `telegram-thu-chi-bot` vừa đẩy lên
5. Bấm **Connect**

### Cấu hình Web Service

Điền đúng như bảng dưới:

| Trường | Giá trị cần điền |
|--------|------------------|
| **Name** | `telegram-thu-chi-bot` (hoặc tên bạn muốn) |
| **Region** | **Singapore** (quan trọng - gần Việt Nam) |
| **Branch** | `main` |
| **Root Directory** | để trống |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | **Free** |

### Thêm Environment Variables

Kéo xuống phần **Environment Variables** → bấm **Add Environment Variable** và thêm lần lượt:

| Key | Value | Ghi chú |
|-----|-------|--------|
| `TELEGRAM_BOT_TOKEN` | Token lấy từ BotFather | Bắt buộc |
| `GEMINI_API_KEY` | Key lấy từ Google AI Studio | Bắt buộc |
| `DATABASE_URL` | Connection string từ Neon | Bắt buộc |
| `WEBHOOK_SECRET` | `abc123xyz789secret` (tự đặt chuỗi bất kỳ) | Bắt buộc |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Khuyến nghị |
| `REMIND_HOUR` | `21` | Giờ nhắc nhở (theo giờ VN) |
| `PYTHON_VERSION` | `3.11.9` | Quan trọng |

> **Mẹo**: Có thể bấm "Add from .env" nếu bạn đã tạo file `.env` local.

6. Sau khi điền xong → bấm **Create Web Service**

7. Đợi Render build (thường 3-7 phút). Theo dõi log:
   - Thấy `Build successful`
   - Thấy `Your service is live`
   - Thấy dòng `Webhook set to: https://...`

8. Copy **URL** của service (dạng `https://telegram-thu-chi-bot-xxxx.onrender.com`)

---

## BƯỚC 6: Kiểm tra bot hoạt động

1. Mở trình duyệt vào URL Render vừa copy
   → Phải thấy dòng JSON: `{"status":"ok", ...}`

2. Vào Telegram → tìm bot bạn vừa tạo → bấm **Start**
3. Gửi `/start`
4. Thử vài lệnh:
   - `chi 50k cafe`
   - `tạo ví MoMo`
   - `danh sách ví`
   - Gửi 1 ảnh hóa đơn
   - Gửi 1 tin nhắn thoại

Nếu bot trả lời → **Thành công!**

---

## BƯỚC 7: Cấu hình UptimeRobot (giữ bot sống 24/7)

Render Free sẽ **tự ngủ** sau khoảng 15 phút không có request. UptimeRobot sẽ ping mỗi 5 phút để bot luôn tỉnh.

1. Vào https://uptimerobot.com → đăng ký / đăng nhập
2. Bấm **+ Add New Monitor**
3. Điền:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `Telegram Thu Chi Bot`
   - **URL**: dán URL Render của bạn (ví dụ `https://telegram-thu-chi-bot-xxxx.onrender.com/`)
   - **Monitoring Interval**: **Every 5 minutes**
4. Bấm **Create Monitor**

Xong! Từ giờ bot gần như không bị sleep nữa.

---

## BƯỚC 8 (Tùy chọn): Nhắc nhở chắc chắn hơn

Nếu muốn chắc chắn nhận nhắc nhở cuối ngày, dùng thêm cron miễn phí:

1. Vào https://cron-job.org → đăng ký
2. Tạo Job mới:
   - Title: `Daily Reminder`
   - URL: `https://your-app.onrender.com/cron/daily-reminder`
   - Method: `POST`
   - Schedule: Every day at **21:00** (chọn timezone Asia/Ho_Chi_Minh hoặc UTC+7)
3. Save

---

## 🛠 Xử lý lỗi thường gặp

| Lỗi | Cách xử lý |
|-----|------------|
| Bot không trả lời | Vào Render → Logs tab xem lỗi. Thường là sai Token hoặc thiếu biến môi trường |
| `DATABASE_URL` lỗi | Kiểm tra connection string Neon có `?sslmode=require` không |
| Webhook không set | Redeploy lại service (Manual Deploy → Clear build cache & deploy) |
| Gemini lỗi quota | Đợi sang ngày hoặc tạo API key mới |
| Build fail vì Python version | Thêm biến `PYTHON_VERSION=3.11.9` |
| Ảnh / Voice không nhận | Kiểm tra log, đôi khi Gemini bị rate limit |

---

## 📁 Cấu trúc project

```
telegram-thu-chi-bot/
├── main.py              # FastAPI + Telegram + Scheduler + Webhook
├── database.py          # asyncpg + Neon Postgres + Wallets
├── ai_handler.py        # Gemini (text + voice + image OCR)
├── charts.py            # Matplotlib tạo biểu đồ
├── requirements.txt
├── .env.example
└── README.md
```

---

## 💡 Mẹo sử dụng sau khi deploy

- Gửi `/start` để xem hướng dẫn nhanh
- Gửi `/wallets` để xem tất cả ví
- Gửi `/help` để xem đầy đủ lệnh
- Muốn tắt nhắc nhở: nhắn `tắt nhắc nhở`
- Muốn đổi giờ nhắc: nhắn `bật nhắc nhở lúc 20h`

---

Chúc bạn deploy thành công và quản lý tiền bạc hiệu quả! 💰

Nếu gặp lỗi ở bước nào, chụp màn hình log hoặc gửi nội dung lỗi, mình sẽ hỗ trợ tiếp.
