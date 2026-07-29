"""Generate a deterministic, original synthetic retail policy/SOP corpus.

The existing eight seed policies remain untouched. This script adds nine related
documents to each existing domain and ten documents to two additional domains,
bringing the corpus to approximately one hundred documents without using an
external model or external data source.
"""

# ruff: noqa: E501 - policy prose remains readable as complete Markdown sentences.

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"


class DomainSpec(TypedDict):
    name: str
    file_prefix: str
    existing: int
    topics: list[tuple[str, str]]


DOMAIN_SPECS: dict[str, DomainSpec] = {
    "RETURN": {
        "name": "退换货与售后",
        "file_prefix": "return_exchange",
        "existing": 1,
        "topics": [
            ("appointment", "预约退货登记"),
            ("cross_store", "跨店退货处理"),
            ("quality_evidence", "质量问题取证"),
            ("fresh_food", "生鲜即时退货"),
            ("large_item_pickup", "大件商品上门取件"),
            ("refund_route", "退款原路返回"),
            ("exchange_inventory", "换货库存锁定"),
            ("gift_return", "赠品退回"),
            ("member_after_sales", "会员专享商品售后"),
        ],
    },
    "PROMO": {
        "name": "促销与营销审批",
        "file_prefix": "promotion",
        "existing": 1,
        "topics": [
            ("member_day", "会员日折扣审批"),
            ("brand_joint", "联合品牌活动"),
            ("gift_budget", "赠品预算管理"),
            ("cross_store_campaign", "异地门店投放"),
            ("live_coupon", "直播优惠券"),
            ("clearance", "清仓促销"),
            ("holiday_hours", "节假日延长营业"),
            ("campaign_review", "促销复盘"),
            ("price_protection", "促销价格保护"),
        ],
    },
    "INVENTORY": {
        "name": "库存、盘点与调拨",
        "file_prefix": "inventory",
        "existing": 1,
        "topics": [
            ("cycle_count", "循环盘点"),
            ("transfer_request", "跨店调拨申请"),
            ("damaged_stock", "残损库存处理"),
            ("slow_moving", "滞销库存预警"),
            ("cold_chain", "冷链库存交接"),
            ("stock_lock", "活动库存锁定"),
            ("inventory_freeze", "盘点冻结窗口"),
            ("shortage_review", "短少差异复核"),
            ("warehouse_receipt", "仓店收货确认"),
        ],
    },
    "MEMBER": {
        "name": "会员、积分与权益",
        "file_prefix": "membership",
        "existing": 1,
        "topics": [
            ("birthday_benefit", "生日权益发放"),
            ("points_reversal", "退货积分冲正"),
            ("tier_upgrade", "会员等级升级"),
            ("coupon_expiry", "会员券到期提醒"),
            ("benefit_transfer", "权益转赠"),
            ("points_exception", "积分异常申诉"),
            ("member_merge", "会员账号合并"),
            ("private_event", "会员专场活动"),
            ("inactive_reactivation", "沉睡会员唤醒"),
        ],
    },
    "PRIVACY": {
        "name": "客户隐私与数据安全",
        "file_prefix": "privacy",
        "existing": 1,
        "topics": [
            ("data_export", "客户数据导出"),
            ("masking", "客户信息脱敏"),
            ("access_review", "数据访问复核"),
            ("retention", "业务数据留存"),
            ("vendor_sharing", "供应商数据共享"),
            ("incident_report", "隐私事件上报"),
            ("camera_access", "门店影像调阅"),
            ("marketing_consent", "营销授权管理"),
            ("account_deletion", "客户账号注销"),
        ],
    },
    "PERFORMANCE": {
        "name": "绩效目标与考核",
        "file_prefix": "performance",
        "existing": 1,
        "topics": [
            ("monthly_target", "月度目标下达"),
            ("regional_adjustment", "区域目标调整"),
            ("new_store_ramp", "新店爬坡考核"),
            ("commission_review", "提成复核"),
            ("attendance_factor", "出勤系数核算"),
            ("customer_score", "服务评分纳入"),
            ("appeal_review", "绩效申诉复核"),
            ("quarterly_calibration", "季度校准会议"),
            ("improvement_plan", "低绩效改进计划"),
        ],
    },
    "PRICE": {
        "name": "定价、折扣与价签",
        "file_prefix": "pricing",
        "existing": 1,
        "topics": [
            ("new_product_price", "新品首发定价"),
            ("regional_price", "区域价格差异"),
            ("markdown", "临期商品降价"),
            ("competitor_match", "竞品价格应对"),
            ("price_tag_change", "价签变更"),
            ("rounding_rule", "收银舍入规则"),
            ("bundle_price", "组合商品定价"),
            ("online_offline_consistency", "线上线下一致价"),
            ("price_audit", "价格稽核"),
        ],
    },
    "ORDER": {
        "name": "订单、支付与异常处理",
        "file_prefix": "order",
        "existing": 1,
        "topics": [
            ("duplicate_payment", "重复支付订单"),
            ("cashier_timeout", "收银超时订单"),
            ("delivery_delay", "配送延迟订单"),
            ("high_value_review", "高价值订单复核"),
            ("coupon_abuse", "优惠券异常使用"),
            ("cancel_after_pick", "拣货后取消"),
            ("invoice_correction", "发票信息更正"),
            ("split_shipment", "拆单配送"),
            ("risk_order_freeze", "风险订单冻结"),
        ],
    },
    "STORE": {
        "name": "门店运营与服务规范",
        "file_prefix": "store_operation",
        "existing": 0,
        "topics": [
            ("opening_check", "开店检查"),
            ("closing_handover", "闭店交接"),
            ("queue_control", "高峰排队管理"),
            ("complaint_reception", "顾客投诉接待"),
            ("service_recovery", "服务补救"),
            ("lost_found", "失物招领"),
            ("temperature_log", "门店温度记录"),
            ("equipment_fault", "设备故障报修"),
            ("emergency_drill", "应急演练"),
            ("display_standard", "陈列标准检查"),
        ],
    },
    "PROCUREMENT": {
        "name": "采购、供应商与物流",
        "file_prefix": "procurement",
        "existing": 0,
        "topics": [
            ("supplier_onboarding", "供应商准入"),
            ("purchase_request", "采购申请"),
            ("quotation_compare", "询价比价"),
            ("delivery_acceptance", "到货验收"),
            ("supplier_score", "供应商评价"),
            ("late_delivery", "供应商延迟交付"),
            ("contract_change", "采购合同变更"),
            ("cold_chain_transport", "冷链运输"),
            ("invoice_match", "采购发票匹配"),
            ("supplier_exit", "供应商退出"),
        ],
    },
}

ROLE_ROTATION = (
    "门店店长",
    "区域运营经理",
    "业务支持专员",
    "财务复核岗",
    "制度管理员",
)
THRESHOLDS = ("500 元", "1,000 元", "3,000 元", "5,000 元", "10,000 元")
DEADLINES = ("当日", "1 个工作日", "2 个工作日", "3 个工作日", "5 个工作日")


def _document_content(
    *,
    domain_name: str,
    title: str,
    topic: str,
    index: int,
) -> str:
    role = ROLE_ROTATION[(index - 1) % len(ROLE_ROTATION)]
    reviewer = ROLE_ROTATION[index % len(ROLE_ROTATION)]
    threshold = THRESHOLDS[(index - 1) % len(THRESHOLDS)]
    deadline = DEADLINES[(index - 1) % len(DEADLINES)]
    return f"""# {title}

## 适用范围

本细则属于零售经营模拟制度库中的“{domain_name}”域，适用于直营门店、区域运营团队和业务支持岗位。凡涉及“{topic}”的申请、执行、复核和归档，均应遵守本细则；加盟门店如无单独约定，参照本细则执行。

## 核心规则

1. “{topic}”由{role}发起，申请信息必须包含业务背景、涉及门店、预计金额或数量、执行时间和责任人。缺少关键字段时不得进入审批。
2. 单次业务金额达到{threshold}或影响两个及以上区域时，应增加{reviewer}复核；涉及客户信息、库存冻结或价格变更时，必须保留系统操作记录。
3. 常规处理时限为{deadline}。遇到节假日、系统故障或供应中断，应在原定时限内记录原因并升级，不得以口头确认替代审批记录。
4. 规则解释以当前生效版本为准；历史单据按照发生时有效的版本核验，但补录记录必须注明实际发生日期。

## 操作流程

1. 发起人先在业务系统登记申请，上传订单、照片、报价单、盘点表或其他必要凭证，并确认数据来源真实完整。
2. {role}完成初审后，根据金额、区域和风险标签分派给{reviewer}。审批人应核对事实、金额、库存或客户授权，不得只依据申请标题判断。
3. 审批通过后由指定执行人办理业务，执行完成后回填实际结果、差异说明和相关单据编号。实际结果与申请不一致时必须重新复核。
4. {reviewer}在{deadline}内完成抽查，并将通过、退回、补充材料和升级四类结果写入记录。涉及异常的单据应关联到对应的原始申请。

## 例外与升级

紧急情况可以先采取避免损失扩大的临时措施，但必须在 24 小时内补齐申请和复核记录。若金额超过{threshold}、连续出现两次相同异常，或涉及客户投诉、合规风险和跨区域争议，应直接升级至区域负责人，不得由单店自行结案。

## 记录与复盘

门店应保留申请、审批、执行和复核记录至少 12 个月。区域团队每月汇总一次“{topic}”的数量、通过率、平均处理时长和异常原因，抽取典型案例更新培训材料；制度管理员负责确认后续补充通知不会与本细则产生未说明的冲突。
"""


def generate_documents(target: Path = DOCUMENTS_DIR) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for code, spec in DOMAIN_SPECS.items():
        name = spec["name"]
        file_prefix = spec["file_prefix"]
        existing = spec["existing"]
        topics = spec["topics"]
        for offset, (slug, topic) in enumerate(topics, 1):
            index = existing + offset
            document_id = f"POL-{code}-{index:03d}"
            title = f"{name}{topic}管理细则"
            month = ((index + len(code)) % 12) + 1
            effective_date = f"2026-{month:02d}-01"
            filename = f"{file_prefix}_{slug}_{index:02d}.md"
            path = target / filename
            if path.exists():
                continue
            content = _document_content(
                domain_name=name,
                title=title,
                topic=topic,
                index=index,
            )
            frontmatter = (
                "---\n"
                f"document_id: {document_id}\n"
                f"title: {title}\n"
                "version: 1.0\n"
                f"effective_date: {effective_date}\n"
                "---\n\n"
            )
            path.write_text(frontmatter + content, encoding="utf-8")
            created.append(path)
    return created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=DOCUMENTS_DIR)
    args = parser.parse_args()
    created = generate_documents(args.target)
    print(f"created={len(created)} target={args.target}")


if __name__ == "__main__":
    main()
