#!/usr/bin/env python3
"""Deterministically derive Zi Wei monthly/daily palace coordinates.

Input is JSON. This helper deliberately does not convert civil dates to lunar
dates or guess software settings. Software month/day anchors are optional: when
they are absent, valid inputs produce an M2 formula-derived chart. See
references/month-day-rules.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BRANCHES = list("子丑寅卯辰巳午未申酉戌亥")
PALACES = ["命", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "交友", "官禄", "田宅", "福德", "父母"]
MUTAGENS = {
    "甲": ["廉贞", "破军", "武曲", "太阳"],
    "乙": ["天机", "天梁", "紫微", "太阴"],
    "丙": ["天同", "天机", "文昌", "廉贞"],
    "丁": ["太阴", "天同", "天机", "巨门"],
    "戊": ["贪狼", "太阴", "右弼", "天机"],
    "己": ["武曲", "贪狼", "天梁", "文曲"],
    "庚": ["太阳", "武曲", "太阴", "天同"],
    "辛": ["巨门", "太阳", "文曲", "文昌"],
    "壬": ["天梁", "紫微", "左辅", "武曲"],
    "癸": ["破军", "巨门", "太阴", "贪狼"],
}
MUTAGEN_NAMES = ["禄", "权", "科", "忌"]


def branch_index(value: str) -> int:
    if value not in BRANCHES:
        raise ValueError(f"无效地支: {value}")
    return BRANCHES.index(value)


def palace_layer(anchor: int) -> dict[str, str]:
    return {name: BRANCHES[(anchor - k) % 12] for k, name in enumerate(PALACES)}


def effective_month(month: int, is_leap: bool, day: int, rule: str) -> int:
    if not 1 <= month <= 12:
        raise ValueError("农历月必须为 1..12")
    if rule == "same_month":
        return month
    if rule == "split_15":
        return month + (1 if is_leap and day >= 16 else 0)
    raise ValueError("leap_rule 必须为 same_month 或 split_15")


def mutagen_projection(stem: str | None, star_positions: dict[str, str], layers: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    if not stem:
        return []
    if stem not in MUTAGENS:
        raise ValueError(f"无效天干: {stem}")
    reverse_layers = {
        layer: {branch: palace for palace, branch in mapping.items()}
        for layer, mapping in layers.items()
    }
    rows = []
    for change, star in zip(MUTAGEN_NAMES, MUTAGENS[stem]):
        branch = star_positions.get(star)
        row: dict[str, Any] = {"四化": change, "星曜": star, "物理地支": branch or "不可得"}
        if branch:
            branch_index(branch)
            for layer, reverse in reverse_layers.items():
                row[f"{layer}宫"] = reverse.get(branch, "不可得")
        rows.append(row)
    return rows


def derive(data: dict[str, Any]) -> dict[str, Any]:
    required = ["yearly_life_branch", "birth_lunar_month", "birth_hour_branch", "target_lunar_month", "leap_rule"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError("缺少字段: " + ", ".join(missing))

    has_target_day = data.get("target_lunar_day") is not None
    lunar_day = int(data["target_lunar_day"]) if has_target_day else None
    if lunar_day is not None and not 1 <= lunar_day <= 30:
        raise ValueError("农历日必须为 1..30，且应先由历法工具验证该月实际天数")

    rule = data["leap_rule"]
    if rule == "split_15" and data.get("birth_is_leap_month") and data.get("birth_lunar_day") is None:
        raise ValueError("出生于闰月且采用 split_15 时必须提供 birth_lunar_day")
    if rule == "split_15" and data.get("target_is_leap_month") and lunar_day is None:
        raise ValueError("目标为闰月且采用 split_15 时必须指定日期，或分别计算前后半月")

    birth_day = int(data.get("birth_lunar_day", 1))
    birth_month = effective_month(
        int(data["birth_lunar_month"]),
        bool(data.get("birth_is_leap_month", False)),
        birth_day,
        rule,
    )
    target_month = effective_month(
        int(data["target_lunar_month"]),
        bool(data.get("target_is_leap_month", False)),
        lunar_day or 1,
        rule,
    )

    yearly_anchor = branch_index(data["yearly_life_branch"])
    hour_index = branch_index(data["birth_hour_branch"])
    calculated_monthly = (yearly_anchor - birth_month + hour_index + target_month) % 12
    supplied_monthly = data.get("software_monthly_life_branch")
    monthly_anchor = branch_index(supplied_monthly) if supplied_monthly else calculated_monthly
    supplied_daily = data.get("software_daily_life_branch")
    if supplied_daily and lunar_day is None:
        raise ValueError("提供 software_daily_life_branch 时必须同时提供 target_lunar_day")
    calculated_daily = (monthly_anchor + lunar_day - 1) % 12 if lunar_day is not None else None
    daily_anchor = branch_index(supplied_daily) if supplied_daily else calculated_daily

    if supplied_monthly or supplied_daily:
        mode = "M1"
        source = "软件锚点 + 确定性补全"
        review_status = "已取得部分软件月日锚点；须检查下列一致性字段"
        display_label = "锚点补全盘"
    else:
        mode = "M2"
        source = "标准斗君/流日公式确定性推导"
        if lunar_day is None:
            review_status = "未经文墨天机流月锚点复核"
            display_label = "公式推导盘｜未经文墨天机流月锚点复核"
        else:
            review_status = "未经文墨天机流月/流日锚点复核"
            display_label = "公式推导盘｜未经文墨天机流月/流日锚点复核"

    layers: dict[str, dict[str, str]] = {
        "流年": palace_layer(yearly_anchor),
        "流月": palace_layer(monthly_anchor),
    }
    if daily_anchor is not None:
        layers["流日"] = palace_layer(daily_anchor)
    star_positions = data.get("star_positions", {})
    missing_transform_inputs = []
    if not data.get("month_stem"):
        missing_transform_inputs.append("month_stem（流月宫位仍可推导；补齐可追溯月干后生成流月四化）")
    if daily_anchor is not None and not data.get("day_stem"):
        missing_transform_inputs.append("day_stem（流日宫位仍可推导；补齐可追溯日干后生成流日四化）")
    result = {
        "模式": mode,
        "来源": source,
        "输出标记": display_label,
        "软件复核状态": review_status,
        "来源可信度": "M1 高于 M2" if mode == "M1" else "低于 M0、M1；可正式解读，不代表已与文墨天机直出一致",
        "闰月规则": rule,
        "四化输入缺失": missing_transform_inputs,
        "流月命宫": BRANCHES[monthly_anchor],
        "流日命宫": BRANCHES[daily_anchor] if daily_anchor is not None else None,
        "公式流月命宫": BRANCHES[calculated_monthly],
        "公式流日命宫": BRANCHES[calculated_daily] if calculated_daily is not None else None,
        "流月锚点一致": None if supplied_monthly is None else branch_index(supplied_monthly) == calculated_monthly,
        "流日锚点一致": None if supplied_daily is None else branch_index(supplied_daily) == calculated_daily,
        "十二宫": layers,
        "流月四化": mutagen_projection(data.get("month_stem"), star_positions, layers),
        "流日四化": mutagen_projection(data.get("day_stem"), star_positions, layers) if daily_anchor is not None else [],
    }
    return result


def self_test() -> None:
    sample = {
        "yearly_life_branch": "午",
        "birth_lunar_month": 8,
        "birth_hour_branch": "子",
        "target_lunar_month": 8,
        "target_lunar_day": 5,
        "leap_rule": "same_month",
        "month_stem": "丙",
        "day_stem": "辛",
        "star_positions": {"天同": "酉", "天机": "丑", "文昌": "申", "廉贞": "午", "巨门": "辰", "太阳": "巳", "文曲": "卯"},
    }
    result = derive(sample)
    assert result["模式"] == "M2"
    assert result["输出标记"] == "公式推导盘｜未经文墨天机流月/流日锚点复核"
    assert result["流月锚点一致"] is None and result["流日锚点一致"] is None
    assert result["流月命宫"] == "午"
    assert result["流日命宫"] == "戌"
    assert result["十二宫"]["流年"]["夫妻"] == "辰"
    assert len(result["流月四化"]) == 4 and len(result["流日四化"]) == 4

    month_only = dict(sample)
    month_only.pop("target_lunar_day")
    month_only.pop("day_stem")
    month_only["target_lunar_month"] = 7
    month_result = derive(month_only)
    assert month_result["模式"] == "M2"
    assert month_result["流月命宫"] == "巳"
    assert month_result["流日命宫"] is None and "流日" not in month_result["十二宫"]
    assert month_result["输出标记"] == "公式推导盘｜未经文墨天机流月锚点复核"

    july_day = dict(sample, target_lunar_month=7, target_lunar_day=5)
    july_day_result = derive(july_day)
    assert july_day_result["模式"] == "M2"
    assert july_day_result["流月命宫"] == "巳" and july_day_result["流日命宫"] == "酉"
    assert len(july_day_result["十二宫"]["流日"]) == 12
    assert july_day_result["输出标记"] == "公式推导盘｜未经文墨天机流月/流日锚点复核"

    leap = dict(sample, target_lunar_month=6, target_lunar_day=16, target_is_leap_month=True, leap_rule="split_15")
    before = dict(leap, target_lunar_day=15)
    assert (branch_index(derive(leap)["流月命宫"]) - branch_index(derive(before)["流月命宫"])) % 12 == 1

    anchored = dict(sample, software_monthly_life_branch="午", software_daily_life_branch="戌")
    anchored_result = derive(anchored)
    assert anchored_result["模式"] == "M1"
    assert anchored_result["流月锚点一致"] is True and anchored_result["流日锚点一致"] is True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, help="JSON 输入文件")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test: ok")
        return
    if not args.input:
        parser.error("需要 JSON 输入文件或 --self-test")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    print(json.dumps(derive(data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
