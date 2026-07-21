import io
from typing import List, Dict, Any
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np

# Font hỗ trợ tiếng Việt tốt hơn (dùng DejaVu)
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False


def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def create_category_chart(by_category: List[Dict[str, Any]], title: str = "Chi tiêu theo danh mục") -> bytes:
    """Biểu đồ tròn (pie) danh mục chi tiêu"""
    if not by_category:
        # Empty chart
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.text(0.5, 0.5, "Chưa có dữ liệu chi tiêu", ha="center", va="center", fontsize=14)
        ax.axis("off")
        return _fig_to_bytes(fig)

    labels = [item["category"] for item in by_category]
    sizes = [item["total"] for item in by_category]
    colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct=lambda pct: f"{pct:.1f}%" if pct > 3 else "",
        startangle=90,
        colors=colors,
        pctdistance=0.75
    )
    ax.legend(
        wedges,
        [f"{l} ({s:,.0f}₫)" for l, s in zip(labels, sizes)],
        title="Danh mục",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1),
        fontsize=9
    )
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    return _fig_to_bytes(fig)


def create_income_expense_chart(income: float, expense: float, title: str = "Thu vs Chi") -> bytes:
    """Biểu đồ cột so sánh thu - chi"""
    fig, ax = plt.subplots(figsize=(7, 5))
    categories = ["Thu nhập", "Chi tiêu"]
    values = [income, expense]
    colors = ["#2ecc71", "#e74c3c"]

    bars = ax.bar(categories, values, color=colors, width=0.5, edgecolor="white", linewidth=1.5)
    ax.set_ylabel("Số tiền (₫)", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}k"))

    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax.annotate(
            f"{val:,.0f}₫",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center", va="bottom", fontsize=10, fontweight="bold"
        )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0, max(values) * 1.2 if max(values) > 0 else 100000)
    return _fig_to_bytes(fig)


def create_daily_chart(daily_stats: List[Dict[str, Any]], days: int = 30, title: str = "Xu hướng thu chi theo ngày") -> bytes:
    """Biểu đồ đường thu/chi theo ngày"""
    if not daily_stats:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.text(0.5, 0.5, "Chưa có dữ liệu", ha="center", va="center", fontsize=14)
        ax.axis("off")
        return _fig_to_bytes(fig)

    # Tổng hợp theo ngày
    from collections import defaultdict
    day_income = defaultdict(float)
    day_expense = defaultdict(float)

    for row in daily_stats:
        day = row["day"]
        if isinstance(day, str):
            day = datetime.strptime(day, "%Y-%m-%d").date()
        if row["type"] == "income":
            day_income[day] += float(row["total"])
        else:
            day_expense[day] += float(row["total"])

    all_days = sorted(set(list(day_income.keys()) + list(day_expense.keys())))
    incomes = [day_income[d] for d in all_days]
    expenses = [day_expense[d] for d in all_days]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(all_days, incomes, marker="o", label="Thu", color="#2ecc71", linewidth=2, markersize=5)
    ax.plot(all_days, expenses, marker="s", label="Chi", color="#e74c3c", linewidth=2, markersize=5)
    ax.fill_between(all_days, expenses, alpha=0.15, color="#e74c3c")

    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.set_ylabel("Số tiền (₫)")
    ax.legend(loc="upper left")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}k"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
    fig.autofmt_xdate(rotation=30)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    return _fig_to_bytes(fig)
