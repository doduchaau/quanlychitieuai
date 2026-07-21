import os
import asyncpg
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Thiếu DATABASE_URL (Neon Postgres connection string)!")

def _clean_dsn(dsn: str) -> str:
    if "?" in dsn:
        base, query = dsn.split("?", 1)
        params = [
            p for p in query.split("&")
            if not p.startswith("sslmode=") and not p.startswith("channel_binding=")
        ]
        if params:
            return base + "?" + "&".join(params)
        return base
    return dsn

_pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Tạo connection pool + bảng nếu chưa có"""
    global _pool
    dsn = _clean_dsn(DATABASE_URL)
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=5,
        ssl="require",
        command_timeout=60,
    )

    async with _pool.acquire() as conn:
        # Bảng ví / tài khoản
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'other',  -- cash, bank, momo, zalopay, credit, other
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, name)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallets_user_id ON wallets(user_id)
        """)

        # Bảng giao dịch (thêm wallet_id)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                wallet_id INT REFERENCES wallets(id) ON DELETE SET NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense', 'transfer')),
                amount DOUBLE PRECISION NOT NULL,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                related_tx_id INT,  -- dùng cho transfer (liên kết 2 giao dịch)
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_wallet_id ON transactions(wallet_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at)
        """)

        # Cài đặt user
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id BIGINT PRIMARY KEY,
                remind_enabled BOOLEAN DEFAULT TRUE,
                remind_hour INT DEFAULT 21,
                timezone TEXT DEFAULT 'Asia/Ho_Chi_Minh',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn():
    async with _pool.acquire() as conn:
        yield conn


# ==================== WALLETS ====================

# Mapping viết tắt phổ biến → tên chuẩn
WALLET_ALIASES = {
    # Ngân hàng
    "vt": "VietinBank", "vtb": "VietinBank", "viettin": "VietinBank",
    "viettinbank": "VietinBank", "vietin": "VietinBank", "vietinbank": "VietinBank",
    "vcb": "Vietcombank", "vietcom": "Vietcombank", "vietcombank": "Vietcombank",
    "tcb": "Techcombank", "techcom": "Techcombank", "techcombank": "Techcombank",
    "mb": "MB Bank", "mbb": "MB Bank", "mbbank": "MB Bank", "mb bank": "MB Bank",
    "acb": "ACB",
    "bidv": "BIDV",
    "vpb": "VPBank", "vpbank": "VPBank",
    "tpb": "TPBank", "tpbank": "TPBank",
    "stb": "Sacombank", "sacombank": "Sacombank",
    "agr": "Agribank", "agribank": "Agribank",
    # Ví điện tử
    "momo": "MoMo",
    "zalopay": "ZaloPay", "zalo": "ZaloPay",
    "shopeepay": "ShopeePay", "shopee": "ShopeePay",
    "viettelpay": "ViettelPay", "viettel": "ViettelPay",
    # Tiền mặt
    "tm": "Tiền mặt", "tien mat": "Tiền mặt", "tiền mặt": "Tiền mặt", "cash": "Tiền mặt",
}


def normalize_wallet_name(name: str) -> str:
    """Chuyển viết tắt thành tên chuẩn nếu có"""
    key = name.strip().lower()
    return WALLET_ALIASES.get(key, name.strip())


async def ensure_default_wallet(user_id: int) -> int:
    """Đảm bảo user có ví mặc định 'Tiền mặt'. Trả về wallet_id"""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM wallets WHERE user_id = $1 AND is_default = TRUE",
            user_id
        )
        if row:
            return row["id"]

        # Tạo ví mặc định
        row = await conn.fetchrow(
            """
            INSERT INTO wallets (user_id, name, type, is_default)
            VALUES ($1, 'Tiền mặt', 'cash', TRUE)
            ON CONFLICT (user_id, name) DO UPDATE SET is_default = TRUE
            RETURNING id
            """,
            user_id
        )
        return row["id"]


async def create_wallet(user_id: int, name: str, type_: str = "other") -> int:
    """Tạo ví mới. Tự động mở rộng viết tắt (VT → VietinBank...). Trả về id"""
    name = normalize_wallet_name(name)  # VT → VietinBank, VCB → Vietcombank...
    async with get_conn() as conn:
        # Đảm bảo có default trước
        await ensure_default_wallet(user_id)

        # Tự đoán type nếu chưa chỉ định rõ
        if type_ == "other":
            lower = name.lower()
            if lower in ("momo",):
                type_ = "momo"
            elif lower in ("zalopay",):
                type_ = "zalopay"
            elif lower == "tiền mặt":
                type_ = "cash"
            elif any(x in lower for x in ["bank", "vietcom", "techcom", "vietin", "mb bank", "acb", "bidv", "tpbank", "vpbank", "sacom", "agri"]):
                type_ = "bank"

        row = await conn.fetchrow(
            """
            INSERT INTO wallets (user_id, name, type, is_default)
            VALUES ($1, $2, $3, FALSE)
            ON CONFLICT (user_id, name) DO UPDATE SET type = $3
            RETURNING id
            """,
            user_id, name, type_
        )
        return row["id"]


async def get_wallets(user_id: int) -> List[Dict[str, Any]]:
    """Lấy danh sách ví + số dư hiện tại của từng ví"""
    await ensure_default_wallet(user_id)
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                w.id, w.name, w.type, w.is_default,
                COALESCE(SUM(
                    CASE 
                        WHEN t.type = 'income' THEN t.amount
                        WHEN t.type = 'expense' THEN -t.amount
                        ELSE 0
                    END
                ), 0) as balance
            FROM wallets w
            LEFT JOIN transactions t ON t.wallet_id = w.id AND t.user_id = w.user_id
            WHERE w.user_id = $1
            GROUP BY w.id, w.name, w.type, w.is_default
            ORDER BY w.is_default DESC, w.name
            """,
            user_id
        )
        return [dict(r) for r in rows]


async def get_wallet_by_name(user_id: int, name: str) -> Optional[Dict[str, Any]]:
    """
    Tìm ví theo tên (không phân biệt hoa thường).
    Hỗ trợ viết tắt: VT → VietinBank, VCB → Vietcombank, TCB → Techcombank...
    """
    original = name.strip()
    normalized = normalize_wallet_name(original)

    async with get_conn() as conn:
        # Thử tên đã chuẩn hóa trước
        row = await conn.fetchrow(
            """
            SELECT id, name, type, is_default
            FROM wallets
            WHERE user_id = $1 AND LOWER(name) = LOWER($2)
            """,
            user_id, normalized
        )
        if row:
            return dict(row)

        # Thử tên gốc (phòng trường hợp user tự đặt tên viết tắt)
        if normalized != original:
            row = await conn.fetchrow(
                """
                SELECT id, name, type, is_default
                FROM wallets
                WHERE user_id = $1 AND LOWER(name) = LOWER($2)
                """,
                user_id, original
            )
            if row:
                return dict(row)

        return None


async def get_wallet_balance(user_id: int, wallet_id: int) -> float:
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(
                CASE 
                    WHEN type = 'income' THEN amount
                    WHEN type = 'expense' THEN -amount
                    ELSE 0
                END
            ), 0) as balance
            FROM transactions
            WHERE user_id = $1 AND wallet_id = $2
            """,
            user_id, wallet_id
        )
        return float(row["balance"])


async def delete_wallet(user_id: int, wallet_id: int) -> bool:
    """Xóa ví (chỉ khi không phải default và không còn giao dịch)"""
    async with get_conn() as conn:
        # Không cho xóa ví default
        row = await conn.fetchrow(
            "SELECT is_default FROM wallets WHERE id = $1 AND user_id = $2",
            wallet_id, user_id
        )
        if not row or row["is_default"]:
            return False

        # Chuyển giao dịch về ví default trước
        default_id = await ensure_default_wallet(user_id)
        await conn.execute(
            "UPDATE transactions SET wallet_id = $1 WHERE wallet_id = $2 AND user_id = $3",
            default_id, wallet_id, user_id
        )
        result = await conn.execute(
            "DELETE FROM wallets WHERE id = $1 AND user_id = $2",
            wallet_id, user_id
        )
        return result == "DELETE 1"


# ==================== TRANSACTIONS ====================

async def add_transaction(
    user_id: int,
    type_: str,
    amount: float,
    category: str,
    description: str = "",
    wallet_id: Optional[int] = None
) -> int:
    if wallet_id is None:
        wallet_id = await ensure_default_wallet(user_id)

    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO transactions (user_id, wallet_id, type, amount, category, description)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            user_id, wallet_id, type_, amount, category, description
        )
        return row["id"]


async def transfer(
    user_id: int,
    from_wallet_id: int,
    to_wallet_id: int,
    amount: float,
    description: str = ""
) -> tuple[int, int]:
    """Chuyển tiền giữa 2 ví. Trả về (tx_out_id, tx_in_id)"""
    if amount <= 0:
        raise ValueError("Số tiền phải > 0")

    async with get_conn() as conn:
        async with conn.transaction():
            # Ghi nhận chi từ ví nguồn
            row_out = await conn.fetchrow(
                """
                INSERT INTO transactions (user_id, wallet_id, type, amount, category, description)
                VALUES ($1, $2, 'expense', $3, 'Chuyển khoản', $4)
                RETURNING id
                """,
                user_id, from_wallet_id, amount, f"Chuyển đến ví khác | {description}".strip(" |")
            )
            # Ghi nhận thu vào ví đích
            row_in = await conn.fetchrow(
                """
                INSERT INTO transactions (user_id, wallet_id, type, amount, category, description, related_tx_id)
                VALUES ($1, $2, 'income', $3, 'Chuyển khoản', $4, $5)
                RETURNING id
                """,
                user_id, to_wallet_id, amount, f"Nhận từ ví khác | {description}".strip(" |"), row_out["id"]
            )
            # Cập nhật related cho giao dịch out
            await conn.execute(
                "UPDATE transactions SET related_tx_id = $1 WHERE id = $2",
                row_in["id"], row_out["id"]
            )
            return row_out["id"], row_in["id"]


async def update_transaction(
    user_id: int,
    tx_id: int,
    type_: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    wallet_id: Optional[int] = None
) -> bool:
    fields = []
    values = []
    idx = 1

    if type_ is not None:
        fields.append(f"type = ${idx}")
        values.append(type_)
        idx += 1
    if amount is not None:
        fields.append(f"amount = ${idx}")
        values.append(amount)
        idx += 1
    if category is not None:
        fields.append(f"category = ${idx}")
        values.append(category)
        idx += 1
    if description is not None:
        fields.append(f"description = ${idx}")
        values.append(description)
        idx += 1
    if wallet_id is not None:
        fields.append(f"wallet_id = ${idx}")
        values.append(wallet_id)
        idx += 1

    if not fields:
        return False

    values.extend([tx_id, user_id])
    query = f"""
        UPDATE transactions
        SET {', '.join(fields)}
        WHERE id = ${idx} AND user_id = ${idx + 1}
    """
    async with get_conn() as conn:
        result = await conn.execute(query, *values)
        return result == "UPDATE 1"


async def delete_transaction(user_id: int, tx_id: int) -> bool:
    async with get_conn() as conn:
        result = await conn.execute(
            "DELETE FROM transactions WHERE id = $1 AND user_id = $2",
            tx_id, user_id
        )
        return result == "DELETE 1"


async def get_transaction(user_id: int, tx_id: int) -> Optional[Dict[str, Any]]:
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT t.id, t.type, t.amount, t.category, t.description, t.created_at,
                   t.wallet_id, w.name as wallet_name
            FROM transactions t
            LEFT JOIN wallets w ON w.id = t.wallet_id
            WHERE t.id = $1 AND t.user_id = $2
            """,
            tx_id, user_id
        )
        return dict(row) if row else None


async def get_balance(user_id: int, wallet_id: Optional[int] = None) -> Dict[str, float]:
    """Tổng số dư. Nếu có wallet_id thì chỉ tính ví đó"""
    async with get_conn() as conn:
        if wallet_id:
            rows = await conn.fetch(
                """
                SELECT type, COALESCE(SUM(amount), 0) as total
                FROM transactions
                WHERE user_id = $1 AND wallet_id = $2 AND type IN ('income', 'expense')
                GROUP BY type
                """,
                user_id, wallet_id
            )
        else:
            rows = await conn.fetch(
                """
                SELECT type, COALESCE(SUM(amount), 0) as total
                FROM transactions
                WHERE user_id = $1 AND type IN ('income', 'expense')
                GROUP BY type
                """,
                user_id
            )
    income = 0.0
    expense = 0.0
    for row in rows:
        if row["type"] == "income":
            income = float(row["total"])
        else:
            expense = float(row["total"])
    return {"income": income, "expense": expense, "balance": income - expense}


async def get_transactions(
    user_id: int,
    limit: int = 10,
    offset: int = 0,
    type_: Optional[str] = None,
    days: Optional[int] = None,
    wallet_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    query = """
        SELECT t.id, t.type, t.amount, t.category, t.description, t.created_at,
               t.wallet_id, w.name as wallet_name
        FROM transactions t
        LEFT JOIN wallets w ON w.id = t.wallet_id
        WHERE t.user_id = $1
    """
    params: list = [user_id]
    idx = 2

    if type_:
        query += f" AND t.type = ${idx}"
        params.append(type_)
        idx += 1

    if wallet_id:
        query += f" AND t.wallet_id = ${idx}"
        params.append(wallet_id)
        idx += 1

    if days:
        query += f" AND t.created_at >= NOW() - INTERVAL '{int(days)} days'"

    query += f" ORDER BY t.created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([limit, offset])

    async with get_conn() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


async def get_report(user_id: int, days: int = 30, wallet_id: Optional[int] = None) -> Dict[str, Any]:
    async with get_conn() as conn:
        wallet_filter = ""
        params = [user_id, str(days)]
        if wallet_id:
            wallet_filter = " AND wallet_id = $3"
            params.append(wallet_id)

        totals = await conn.fetch(
            f"""
            SELECT type, COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE user_id = $1 AND type IN ('income', 'expense')
              AND created_at >= NOW() - ($2 || ' days')::INTERVAL
              {wallet_filter}
            GROUP BY type
            """,
            *params
        )
        by_cat = await conn.fetch(
            f"""
            SELECT category, COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE user_id = $1 AND type = 'expense'
              AND created_at >= NOW() - ($2 || ' days')::INTERVAL
              {wallet_filter}
            GROUP BY category
            ORDER BY total DESC
            """,
            *params
        )

    income = 0.0
    expense = 0.0
    for row in totals:
        if row["type"] == "income":
            income = float(row["total"])
        else:
            expense = float(row["total"])

    return {
        "days": days,
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "by_category": [{"category": r["category"], "total": float(r["total"])} for r in by_cat]
    }


async def get_daily_stats(user_id: int, days: int = 30) -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') as day,
                type,
                COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE user_id = $1 
              AND type IN ('income', 'expense')
              AND created_at >= NOW() - ($2 || ' days')::INTERVAL
            GROUP BY day, type
            ORDER BY day
            """,
            user_id, str(days)
        )
    return [dict(r) for r in rows]


async def get_month_prediction_data(user_id: int) -> Dict[str, Any]:
    today = datetime.now().date()
    first_day = today.replace(day=1)

    days_passed = (today - first_day).days + 1
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    days_in_month = (next_month - first_day).days
    remaining_days = max(0, days_in_month - days_passed)

    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE user_id = $1 AND type = 'expense' AND created_at >= $2
            """,
            user_id, first_day
        )
        expense_so_far = float(row["total"])

        row_income = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE user_id = $1 AND type = 'income' AND created_at >= $2
            """,
            user_id, first_day
        )
        income_so_far = float(row_income["total"])

        row_today = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE user_id = $1 
              AND type = 'expense'
              AND DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') = CURRENT_DATE
            """,
            user_id
        )
        expense_today = float(row_today["total"])

    avg_daily = expense_so_far / days_passed if days_passed > 0 else 0.0
    predicted_remaining = avg_daily * remaining_days
    predicted_total = expense_so_far + predicted_remaining

    return {
        "days_passed": days_passed,
        "remaining_days": remaining_days,
        "days_in_month": days_in_month,
        "expense_so_far": expense_so_far,
        "income_so_far": income_so_far,
        "expense_today": expense_today,
        "avg_daily": avg_daily,
        "predicted_remaining": predicted_remaining,
        "predicted_total": predicted_total,
        "balance_so_far": income_so_far - expense_so_far
    }


async def get_active_users(days: int = 30) -> List[int]:
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT user_id
            FROM transactions
            WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL
            """,
            str(days)
        )
        return [r["user_id"] for r in rows]


async def set_remind_setting(user_id: int, enabled: bool = True, hour: int = 21):
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO user_settings (user_id, remind_enabled, remind_hour)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
            SET remind_enabled = $2, remind_hour = $3, updated_at = NOW()
            """,
            user_id, enabled, hour
        )


async def get_users_to_remind(hour: int = 21) -> List[int]:
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT t.user_id
            FROM transactions t
            LEFT JOIN user_settings s ON t.user_id = s.user_id
            WHERE t.created_at >= NOW() - INTERVAL '60 days'
              AND (s.remind_enabled IS NULL OR s.remind_enabled = TRUE)
              AND (s.remind_hour IS NULL OR s.remind_hour = $1)
            """,
            hour
        )
        return [r["user_id"] for r in rows]
