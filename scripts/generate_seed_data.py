"""Generate deterministic retail demo data as a MySQL initialization script."""

from __future__ import annotations

import random
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

RANDOM_SEED = 20260722
ORDER_COUNT = 4_000
CUSTOMER_COUNT = 500

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "seed" / "demo_data.sql"

REGION_CITIES = {
    "华东": ["上海", "杭州", "南京"],
    "华南": ["广州", "深圳", "厦门"],
    "华北": ["北京", "天津", "石家庄"],
    "西南": ["成都", "重庆", "昆明"],
}
CATEGORIES = {
    "食品饮料": ["坚果礼盒", "苏打水", "挂耳咖啡", "燕麦片", "酸奶"],
    "家居日用": ["抽纸", "洗衣液", "保鲜袋", "毛巾", "垃圾袋"],
    "数码配件": ["充电器", "数据线", "无线鼠标", "蓝牙耳机", "键盘"],
    "个护美妆": ["洗发水", "洁面乳", "牙膏", "护手霜", "防晒霜"],
    "文体办公": ["中性笔", "笔记本", "文件夹", "羽毛球", "瑜伽垫"],
    "母婴用品": ["纸尿裤", "婴儿湿巾", "儿童水杯", "积木", "绘本"],
}
BRANDS = ["青禾", "云岚", "星桥", "原野", "简物", "新橙"]
SEGMENTS = ["普通会员", "银卡会员", "金卡会员", "企业客户"]
RETURN_REASONS = ["质量问题", "尺寸或规格不符", "重复购买", "包装破损", "不再需要"]


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return sql_string(value.strftime("%Y-%m-%d %H:%M:%S"))
    return sql_string(value.isoformat())


def random_datetime(rng: random.Random, start: datetime, end: datetime) -> datetime:
    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, seconds))


def month_starts(start: date, end: date) -> list[date]:
    values: list[date] = []
    current = start.replace(day=1)
    while current <= end:
        values.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return values


def insert_statement(table: str, columns: list[str], rows: list[tuple[object, ...]]) -> str:
    def encode(value: object) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, (date, datetime)):
            return sql_date(value)
        if isinstance(value, str):
            return sql_string(value)
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)

    values = ",\n".join("(" + ", ".join(encode(value) for value in row) + ")" for row in rows)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n{values};\n"


def batched_insert(
    table: str,
    columns: list[str],
    rows: list[tuple[object, ...]],
    *,
    batch_size: int = 500,
) -> list[str]:
    return [
        insert_statement(table, columns, rows[index : index + batch_size])
        for index in range(0, len(rows), batch_size)
    ]


def build_data() -> dict[str, list[tuple[object, ...]]]:
    rng = random.Random(RANDOM_SEED)

    stores: list[tuple[object, ...]] = []
    for region, cities in REGION_CITIES.items():
        for city in cities:
            stores.append(
                (
                    len(stores) + 1,
                    f"{city}{rng.choice(['中心', '万象', '悦享'])}店",
                    region,
                    city,
                    date(
                        2021 + rng.randint(0, 3),
                        rng.randint(1, 12),
                        rng.randint(1, 25),
                    ),
                )
            )

    products: list[tuple[object, ...]] = []
    for category, names in CATEGORIES.items():
        for brand in BRANDS[:2]:
            for name in names:
                price = Decimal(rng.randrange(1500, 18000)) / 100
                cost = (price * Decimal(str(rng.uniform(0.48, 0.72)))).quantize(Decimal("0.01"))
                products.append((len(products) + 1, f"{brand}{name}", category, brand, price, cost))

    customers: list[tuple[object, ...]] = [
        (
            customer_id,
            rng.choices(SEGMENTS, weights=[55, 25, 15, 5], k=1)[0],
            date(2022, 1, 1) + timedelta(days=rng.randint(0, 1_460)),
        )
        for customer_id in range(1, CUSTOMER_COUNT + 1)
    ]

    order_start = datetime(2025, 1, 1)
    order_end = datetime(2026, 6, 30, 23, 59, 59)
    orders: list[tuple[object, ...]] = []
    order_items: list[tuple[object, ...]] = []
    returns: list[tuple[object, ...]] = []
    item_id = 1
    return_id = 1

    for order_id in range(1, ORDER_COUNT + 1):
        order_date = random_datetime(rng, order_start, order_end)
        status = rng.choices(["completed", "cancelled"], weights=[95, 5], k=1)[0]
        orders.append(
            (
                order_id,
                rng.randint(1, len(stores)),
                rng.randint(1, CUSTOMER_COUNT),
                order_date,
                status,
            )
        )
        chosen_products = rng.sample(range(1, len(products) + 1), rng.randint(1, 4))
        for product_id in chosen_products:
            list_price = products[product_id - 1][4]
            assert isinstance(list_price, Decimal)
            discount = Decimal(str(rng.choice([0, 0, 0.05, 0.10, 0.15]))).quantize(
                Decimal("0.0001")
            )
            order_items.append(
                (item_id, order_id, product_id, rng.randint(1, 3), list_price, discount)
            )
            if status == "completed" and rng.random() < 0.035:
                return_day = min(
                    order_date.date() + timedelta(days=rng.randint(1, 14)),
                    order_end.date(),
                )
                returns.append(
                    (return_id, order_id, product_id, rng.choice(RETURN_REASONS), return_day)
                )
                return_id += 1
            item_id += 1

    inventory: list[tuple[object, ...]] = []
    inventory_id = 1
    for snapshot in (date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 30)):
        for store_id in range(1, len(stores) + 1):
            for product_id in range(1, len(products) + 1):
                inventory.append(
                    (inventory_id, store_id, product_id, rng.randint(0, 180), snapshot)
                )
                inventory_id += 1

    targets: list[tuple[object, ...]] = []
    target_id = 1
    for month in month_starts(date(2025, 1, 1), date(2026, 6, 1)):
        days = monthrange(month.year, month.month)[1]
        seasonal = Decimal("1.20") if month.month in {6, 11, 12} else Decimal("1.00")
        for store_id in range(1, len(stores) + 1):
            base = Decimal(110_000 + store_id * 3_500 + days * 600)
            targets.append(
                (target_id, store_id, month, (base * seasonal).quantize(Decimal("0.01")))
            )
            target_id += 1

    return {
        "stores": stores,
        "products": products,
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
        "returns": returns,
        "inventory": inventory,
        "sales_targets": targets,
    }


def main() -> None:
    data = build_data()
    statements = [
        "-- Generated by scripts/generate_seed_data.py; do not edit manually.\n",
        "SET NAMES utf8mb4;\n",
        "SET FOREIGN_KEY_CHECKS = 0;\n",
    ]
    columns = {
        "stores": ["store_id", "store_name", "region", "city", "open_date"],
        "products": ["product_id", "product_name", "category", "brand", "price", "cost"],
        "customers": ["customer_id", "customer_segment", "register_date"],
        "orders": ["order_id", "store_id", "customer_id", "order_date", "status"],
        "order_items": [
            "order_item_id",
            "order_id",
            "product_id",
            "quantity",
            "sale_price",
            "discount",
        ],
        "returns": ["return_id", "order_id", "product_id", "return_reason", "return_date"],
        "inventory": ["inventory_id", "store_id", "product_id", "stock_qty", "snapshot_date"],
        "sales_targets": ["target_id", "store_id", "target_month", "revenue_target"],
    }
    for table_name in columns:
        statements.extend(batched_insert(table_name, columns[table_name], data[table_name]))
    statements.append("SET FOREIGN_KEY_CHECKS = 1;\n")
    OUTPUT_PATH.write_text("\n".join(statements), encoding="utf-8")
    summary = ", ".join(f"{table}={len(rows)}" for table, rows in data.items())
    print(f"Generated {OUTPUT_PATH}: {summary}")


if __name__ == "__main__":
    main()
