from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from pages._bottom_nav import render_page_nav
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
)
from utils.file_reader import TEXT_FILE_ENCODINGS, normalize_name, read_uploaded_file


VENUE_COL = "场馆名称"
WEIGHT_COLS = [
    "通用赛事物资(kg)",
    "专项运动器材(kg)",
    "医疗物资(kg)",
    "IT设备(kg)",
    "生活保障物资(kg)",
]
TOTAL_COL = "总需求(kg)"
DEFAULT_MATERIAL_BASE_NAMES = [col.replace("(kg)", "").strip() for col in WEIGHT_COLS]

_EXCLUDE_COL_KEYWORDS = {"合计", "总计", "总需求", "total", "小计", "subtotal", "sum"}
_SKIP_COL_KEYWORDS = {"序号", "备注", "编号", "no", "remark", "note", "index"}
_PRIMARY_VENUE_HEADER_KEYS = {"场馆名称", "场馆名", "场馆", "venue", "venuename"}
_SECONDARY_VENUE_HEADER_KEYS = {"name"}
_SUMMARY_ROW_KEYWORDS = {"合计", "总计", "汇总", "小计", "total", "subtotal", "sum"}
_NON_MATERIAL_KEYWORDS = {
    "序号",
    "编号",
    "no",
    "index",
    "备注",
    "remark",
    "note",
    "comment",
    "场馆",
    "名称",
    "地址",
    "address",
    "addr",
    "位置",
    "position",
    "项目",
    "event",
    "sport",
    "project",
    "经度",
    "纬度",
    "longitude",
    "latitude",
    "lng",
    "lat",
    "坐标",
    "联系人",
    "联系",
    "电话",
    "手机",
    "mobile",
    "phone",
    "tel",
    "email",
    "mail",
    "日期",
    "date",
    "时间",
    "time",
    "数量",
    "count",
    "qty",
    "quantity",
    "人数",
    "预算",
    "金额",
    "price",
    "单价",
    "cost",
    "需求",
    "需求量",
    "weight",
    "demand",
    "合计",
    "总计",
    "总需求",
    "subtotal",
    "sum",
    "total",
}
_MATERIAL_HEADER_HINTS = {
    "物资",
    "器材",
    "设备",
    "装备",
    "耗材",
    "用品",
    "supply",
    "material",
    "equipment",
    "kit",
    "medical",
    "sport",
    "it设备",
}
_UNIT_HEADER_HINTS = {"kg", "公斤", "千克", "克", "吨", "lb", "lbs", "磅", "斤"}
_WEIGHT_UNITS_TO_KG = {
    "kg": 1.0,
    "公斤": 1.0,
    "千克": 1.0,
    "g": 0.001,
    "克": 0.001,
    "t": 1000.0,
    "吨": 1000.0,
    "ton": 1000.0,
    "tons": 1000.0,
    "斤": 0.5,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "磅": 0.45359237,
}
_WEIGHT_VALUE_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d+)?|\.\d+))([a-zA-Z\u4e00-\u9fff]+)?$")
_MAX_REASONABLE_WEIGHT_KG = 1_000_000.0
_WEIGHT_ROUND_DECIMALS = 6


@dataclass
class MaterialUploadResult:
    numeric_df: pd.DataFrame
    display_df: pd.DataFrame
    material_columns: list[str]
    warnings: list[str]
    stats: dict[str, int]
    error: str | None = None


def init_state() -> None:
    if "demands_df" not in st.session_state:
        st.session_state.demands_df = None
    if "demands_display_df" not in st.session_state:
        st.session_state.demands_display_df = None
    if "demands" not in st.session_state:
        st.session_state.demands = {}
    if "material_demands" not in st.session_state:
        st.session_state.material_demands = {}
    if "material_columns" not in st.session_state:
        st.session_state.material_columns = DEFAULT_MATERIAL_BASE_NAMES.copy()


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    try:
        text = unicodedata.normalize("NFKC", text)
    except Exception:
        pass
    return text.replace("\u3000", " ").strip()


def _normalize_header_key(value: object) -> str:
    text = _normalize_text(value).lower()
    return re.sub(r"[\s_\-]+", "", text)


def _is_primary_venue_header(value: object) -> bool:
    key = _normalize_header_key(value)
    if not key:
        return False
    return key in _PRIMARY_VENUE_HEADER_KEYS or "场馆名称" in key or "场馆名" in key


def _is_venue_header_name(value: object) -> bool:
    key = _normalize_header_key(value)
    if not key:
        return False
    if _is_primary_venue_header(value):
        return True
    return key in _SECONDARY_VENUE_HEADER_KEYS


def _looks_like_material_header(value: object) -> bool:
    key = _normalize_header_key(value)
    if not key or _is_venue_header_name(value):
        return False
    if any(keyword in key for keyword in _NON_MATERIAL_KEYWORDS):
        return False
    return any(keyword in key for keyword in (_MATERIAL_HEADER_HINTS | _UNIT_HEADER_HINTS))


def _material_col_to_base_name(col_name: str) -> str:
    text = _normalize_text(col_name)
    text = re.sub(
        r"[\(\[（【]?\s*(kg|KG|公斤|公斤|千克|g|G|克|t|T|吨|lb|lbs|LB|LBS|磅|斤)\s*[\)\]）】]?$",
        "",
        text,
    )
    return text.rstrip(":/：-_ ").strip()


def _get_material_display_columns(base_names: list[str] | None = None) -> list[str]:
    return [_format_material_display_name(name) for name in (base_names or [])]


def _collect_material_base_names(*dfs: pd.DataFrame | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(base_name: str) -> None:
        normalized = _material_col_to_base_name(base_name)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        ordered.append(normalized)

    demands_df = st.session_state.get("demands_df")
    if isinstance(demands_df, pd.DataFrame):
        for col in demands_df.columns:
            if col not in {VENUE_COL, TOTAL_COL} and str(col).strip() not in _SKIP_COL_KEYWORDS:
                add(col)

    for df in dfs:
        if not isinstance(df, pd.DataFrame):
            continue
        for col in df.columns:
            col_name = str(col).strip()
            if col_name in {VENUE_COL, TOTAL_COL, "序号"}:
                continue
            if col_name.lower() in _SKIP_COL_KEYWORDS:
                continue
            add(col_name)

    for venue_data in (st.session_state.get("material_demands") or {}).values():
        if isinstance(venue_data, dict):
            for base_name in venue_data.keys():
                add(base_name)

    for demand in (st.session_state.get("demands") or {}).values():
        if not isinstance(demand, dict):
            continue
        for key in demand.keys():
            if key != "总需求":
                add(key)

    saved_material_columns = st.session_state.get("material_columns", []) or []
    if ordered and set(saved_material_columns).issubset(set(DEFAULT_MATERIAL_BASE_NAMES)):
        saved_material_columns = []

    for base_name in saved_material_columns:
        add(base_name)

    return ordered or DEFAULT_MATERIAL_BASE_NAMES.copy()


def _style_display_df(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    format_map: dict[str, object] = {}
    table_styles: list[dict[str, str]] = []

    for col in df.columns:
        if col == VENUE_COL:
            continue
        if col == "序号":
            format_map[col] = lambda value: f"{int(float(value or 0))}"
        else:
            format_map[col] = _format_numeric_display

    styled = df.style.format(format_map, na_rep="0")
    for idx, col in enumerate(df.columns):
        align = "left" if col == VENUE_COL else "center"
        table_styles.append(
            {"selector": f"th.col_heading.level0.col{idx}", "props": f"text-align: {align};"}
        )
    if table_styles:
        styled = styled.set_table_styles(table_styles, overwrite=False)
    if VENUE_COL in df.columns:
        styled = styled.set_properties(subset=[VENUE_COL], **{"text-align": "left"})
    centered_cols = [col for col in df.columns if col != VENUE_COL]
    if centered_cols:
        styled = styled.set_properties(subset=centered_cols, **{"text-align": "center"})
    return styled


def build_empty_df(venue_names: list[str], material_columns: list[str] | None = None) -> pd.DataFrame:
    display_cols = _get_material_display_columns(material_columns or _collect_material_base_names())
    return pd.DataFrame({VENUE_COL: venue_names, **{col: [0.0] * len(venue_names) for col in display_cols}})


def _is_reasonable_weight_kg(value: float) -> bool:
    return 0 <= value <= _MAX_REASONABLE_WEIGHT_KG


def _coerce_weight_value(
    value: object,
    *,
    allow_plain_number: bool,
) -> tuple[float | None, str, bool]:
    if value is None or pd.isna(value):
        return 0.0, "empty", False
    if isinstance(value, bool):
        return None, "invalid", False

    if isinstance(value, (int, float, Decimal)):
        numeric_value = float(value)
        if pd.isna(numeric_value):
            return 0.0, "empty", False
        if numeric_value < 0 or not _is_reasonable_weight_kg(numeric_value):
            return None, "invalid", False
        if allow_plain_number:
            return numeric_value, "valid", False
        return None, "invalid", False

    text = _normalize_text(value).replace(",", "").replace("，", "")
    if not text or text.lower() == "nan":
        return 0.0, "empty", False

    compact_text = re.sub(r"\s+", "", text)
    match = _WEIGHT_VALUE_RE.fullmatch(compact_text)
    if not match:
        return None, "invalid", False

    number = float(match.group(1))
    if number < 0:
        return None, "invalid", False

    unit_raw = match.group(2) or ""
    unit_key = _normalize_header_key(unit_raw)
    if unit_key:
        factor = _WEIGHT_UNITS_TO_KG.get(unit_key)
        if factor is None:
            return None, "invalid", True
        weight_kg = number * factor
        if not _is_reasonable_weight_kg(weight_kg):
            return None, "invalid", True
        return weight_kg, "valid", True

    if not allow_plain_number or not _is_reasonable_weight_kg(number):
        return None, "invalid", False
    return number, "valid", False


def _parse_weight_to_kg(value) -> float:
    """将带单位的字符串或纯数字统一换算为 kg 浮点数。"""
    if pd.isna(value):
        return 0.0

    s = _normalize_text(value).replace(",", "").replace("，", "").replace(" ", "")
    if not s or s.lower() == "nan":
        return 0.0

    match = re.match(
        r"^([+-]?\d+(?:\.\d+)?)\s*(kg|千克|公斤|g|克|t|吨|ton|斤|lb|lbs|磅)?$",
        s,
        re.IGNORECASE,
    )
    if not match:
        num_match = re.search(r"([+-]?\d+(?:\.\d+)?)", s)
        if num_match:
            return float(num_match.group(1))
        return 0.0

    num = float(match.group(1))
    unit = _normalize_header_key(match.group(2) or "")

    conversion = {
        "": 1.0,
        "kg": 1.0,
        "千克": 1.0,
        "公斤": 1.0,
        "g": 0.001,
        "克": 0.001,
        "t": 1000.0,
        "吨": 1000.0,
        "ton": 1000.0,
        "斤": 0.5,
        "lb": 0.4536,
        "lbs": 0.4536,
        "磅": 0.4536,
    }
    return num * conversion.get(unit, 1.0)


def _is_material_col(col_name: str) -> bool:
    """判断一个列名是否为物资分项列。"""
    col_lower = str(col_name).strip().lower()
    for kw in _EXCLUDE_COL_KEYWORDS:
        if kw in col_lower:
            return False
    for kw in _SKIP_COL_KEYWORDS:
        if kw in col_lower:
            return False
    if "场馆名称" in str(col_name):
        return False
    return True


def _format_numeric_display(value: object) -> str:
    if pd.isna(value):
        return "0"

    if isinstance(value, float):
        value = _round_weight(value)

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

    text = format(decimal_value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _extract_preserved_display_value(value: object, numeric_value: float) -> str:
    if pd.isna(value):
        return "0"

    text = _normalize_text(value).replace(",", "").replace(" ", "")
    if not text or text.lower() == "nan":
        return "0"

    match = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z\u4e00-\u9fff]*)$", text, re.IGNORECASE)
    if not match:
        return _format_numeric_display(numeric_value)

    number_text = match.group(1)
    unit = _normalize_header_key(match.group(2) or "")
    if unit in {"", "kg", "千克", "公斤", "公斤"}:
        return number_text
    return _format_numeric_display(numeric_value)


def _format_material_display_name(col_name: str) -> str:
    base = _material_col_to_base_name(col_name)
    return f"{base}(kg)"


def _round_weight(value: object, decimals: int = _WEIGHT_ROUND_DECIMALS) -> float:
    try:
        numeric_value = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(numeric_value):
        return 0.0
    return round(numeric_value, decimals)


def _sum_weight_values(values: list[object], decimals: int = _WEIGHT_ROUND_DECIMALS) -> float:
    return round(sum(_round_weight(value, decimals) for value in values), decimals)


def _normalize_display_value(value: object) -> str:
    if pd.isna(value):
        return "0"
    text = _normalize_text(value)
    return text if text else "0"


def normalize_display_df(df: pd.DataFrame, material_columns: list[str] | None = None) -> pd.DataFrame:
    clean = df.copy()
    target_material_cols = _get_material_display_columns(material_columns or _collect_material_base_names(clean))

    if VENUE_COL not in clean.columns:
        clean[VENUE_COL] = ""

    for col in target_material_cols:
        if col not in clean.columns:
            clean[col] = "0"
        clean[col] = clean[col].apply(_normalize_display_value)

    return clean[[VENUE_COL] + target_material_cols]


def normalize_df(df: pd.DataFrame, material_columns: list[str] | None = None) -> pd.DataFrame:
    clean = df.copy()
    target_material_cols = _get_material_display_columns(material_columns or _collect_material_base_names(clean))

    if VENUE_COL not in clean.columns:
        clean[VENUE_COL] = ""

    for col in target_material_cols:
        if col not in clean.columns:
            clean[col] = 0.0
        clean[col] = pd.to_numeric(clean[col], errors="coerce").fillna(0.0).round(_WEIGHT_ROUND_DECIMALS)

    clean = clean[[VENUE_COL] + target_material_cols]
    clean[TOTAL_COL] = (
        clean[target_material_cols].sum(axis=1).round(_WEIGHT_ROUND_DECIMALS)
        if target_material_cols else 0.0
    )
    return clean


def parse_online_editor_df(
    df: pd.DataFrame,
    material_columns: list[str] | None = None,
    *,
    strict: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    base_names = material_columns or _collect_material_base_names(df)
    material_display_cols = _get_material_display_columns(base_names)
    display_source = normalize_display_df(df, base_names)

    numeric_rows: list[dict[str, float | str]] = []
    display_rows: list[dict[str, str]] = []
    errors: list[str] = []

    for row_index, row in display_source.iterrows():
        venue_display = str(row.get(VENUE_COL, "")).strip()
        numeric_row: dict[str, float | str] = {VENUE_COL: venue_display}
        display_row: dict[str, str] = {VENUE_COL: venue_display}

        for col in material_display_cols:
            raw_text = _normalize_display_value(row.get(col, "0")).replace(",", "")
            try:
                decimal_value = Decimal(raw_text)
            except InvalidOperation:
                if strict:
                    errors.append(f"第 {row_index + 1} 行 {venue_display or '未命名场馆'} 的“{col}”不是有效数字。")
                decimal_value = Decimal("0")
                raw_text = "0"

            if decimal_value < 0:
                if strict:
                    errors.append(f"第 {row_index + 1} 行 {venue_display or '未命名场馆'} 的“{col}”不能为负数。")
                decimal_value = Decimal("0")
                raw_text = "0"

            numeric_row[col] = float(decimal_value)
            display_row[col] = raw_text

        numeric_rows.append(numeric_row)
        display_rows.append(display_row)

    numeric_df = normalize_df(pd.DataFrame(numeric_rows), base_names)
    display_df = normalize_display_df(pd.DataFrame(display_rows), base_names)
    return numeric_df, display_df, errors


def _find_header_row_idx(raw_df: pd.DataFrame) -> int | None:
    best_idx: int | None = None
    best_score = -1

    for idx in range(min(30, len(raw_df))):
        row_values = [_normalize_text(value) for value in raw_df.iloc[idx].tolist()]
        non_empty_values = [value for value in row_values if value]
        if not non_empty_values:
            continue

        primary_hits = sum(1 for value in non_empty_values if _is_primary_venue_header(value))
        secondary_hits = sum(1 for value in non_empty_values if _normalize_header_key(value) in _SECONDARY_VENUE_HEADER_KEYS)
        venue_score = primary_hits * 10 + secondary_hits * 3
        if venue_score <= 0:
            continue

        material_hits = sum(1 for value in non_empty_values if _looks_like_material_header(value))
        score = venue_score + material_hits * 3 + len(non_empty_values)
        if score > best_score:
            best_idx = idx
            best_score = score

    return best_idx


def _smart_read_excel(uploaded_file) -> tuple[pd.DataFrame | None, str | None]:
    filename = uploaded_file.name.lower()
    uploaded_file.seek(0)

    try:
        if filename.endswith((".xlsx", ".xls")):
            raw_df = pd.read_excel(uploaded_file, header=None, nrows=30)
        elif filename.endswith(".csv"):
            raw_df = None
            for encoding in TEXT_FILE_ENCODINGS:
                try:
                    uploaded_file.seek(0)
                    raw_df = pd.read_csv(uploaded_file, header=None, nrows=30, encoding=encoding)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if raw_df is None:
                return None, "无法识别文件编码"
        else:
            uploaded_file.seek(0)
            return read_uploaded_file(uploaded_file)
    except Exception as exc:
        return None, f"文件读取失败: {exc}"

    header_row_idx = None
    for idx in range(min(20, len(raw_df))):
        row_values = [str(value).strip() for value in raw_df.iloc[idx].values]
        if any("场馆名称" in value for value in row_values):
            header_row_idx = idx
            break

    if header_row_idx is None:
        uploaded_file.seek(0)
        return read_uploaded_file(uploaded_file)

    uploaded_file.seek(0)
    try:
        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file, header=header_row_idx)
        else:
            df = None
            for encoding in TEXT_FILE_ENCODINGS:
                try:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, header=header_row_idx, encoding=encoding)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if df is None:
                return None, "无法识别文件编码"
    except Exception as exc:
        return None, f"使用检测到的表头重新读取失败: {exc}"

    df.columns = [str(col).strip() for col in df.columns]
    df = df.dropna(how="all").reset_index(drop=True)
    return df, None


def _find_venue_column(columns: pd.Index) -> str | None:
    for col in columns:
        if _is_primary_venue_header(col):
            return col
    for col in columns:
        if _is_venue_header_name(col):
            return col
    for col in columns:
        col_key = _normalize_header_key(col)
        if "场馆" in col_key or col_key in {"venue", "venuename"}:
            return col
    return None


def _parse_weight_series(series: pd.Series, *, allow_plain_number: bool) -> dict[str, object]:
    numeric_values: list[float] = []
    display_values: list[str] = []
    valid_count = 0
    invalid_count = 0
    non_empty_count = 0

    for value in series:
        weight_kg, status, _ = _coerce_weight_value(value, allow_plain_number=allow_plain_number)
        if status == "empty":
            numeric_values.append(0.0)
            display_values.append("0")
            continue

        non_empty_count += 1
        if status == "valid":
            valid_count += 1
            numeric_value = float(weight_kg or 0.0)
            numeric_values.append(numeric_value)
            display_values.append(_extract_preserved_display_value(value, numeric_value))
        else:
            invalid_count += 1
            numeric_values.append(0.0)
            display_values.append("0")

    return {
        "numeric": pd.Series(numeric_values, index=series.index, dtype=float),
        "display": pd.Series(display_values, index=series.index, dtype="object"),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "non_empty_count": non_empty_count,
    }


def _classify_material_column(col_name: str, series: pd.Series) -> dict[str, object]:
    header_label = _normalize_text(col_name)
    header_key = _normalize_header_key(header_label)

    if not header_key:
        return {"include": False, "reason": "列名为空", "non_empty_count": 0}
    if _is_venue_header_name(header_label):
        return {"include": False, "reason": "场馆列", "non_empty_count": 0}
    if any(keyword in header_key for keyword in _NON_MATERIAL_KEYWORDS):
        return {
            "include": False,
            "reason": "属于地址/备注/联系方式等元数据列",
            "non_empty_count": int(series.notna().sum()),
        }

    header_has_material_hint = any(keyword in header_key for keyword in _MATERIAL_HEADER_HINTS)
    header_has_unit_hint = any(keyword in header_key for keyword in _UNIT_HEADER_HINTS)

    strict_result = _parse_weight_series(series, allow_plain_number=False)
    loose_result = _parse_weight_series(series, allow_plain_number=True)
    non_empty_count = int(loose_result["non_empty_count"])
    if non_empty_count <= 0:
        return {"include": False, "reason": "列中没有可读取的数据", "non_empty_count": 0}

    strict_ratio = float(strict_result["valid_count"]) / non_empty_count
    loose_ratio = float(loose_result["valid_count"]) / non_empty_count
    min_valid_count = min(2, non_empty_count)

    chosen_result = strict_result
    include_column = False

    if header_has_material_hint or header_has_unit_hint:
        chosen_result = loose_result
        include_column = loose_result["valid_count"] > 0 and loose_ratio >= 0.35
    elif strict_result["valid_count"] > 0 and strict_ratio >= 0.6:
        chosen_result = strict_result
        include_column = True
    elif loose_result["valid_count"] >= min_valid_count and loose_ratio >= 0.8:
        chosen_result = loose_result
        include_column = True

    if not include_column:
        return {
            "include": False,
            "reason": "可识别为重量的单元格比例不足",
            "non_empty_count": non_empty_count,
        }

    base_name = _material_col_to_base_name(header_label) or header_label
    warning = None
    if chosen_result["invalid_count"]:
        warning = (
            f"列“{header_label}”中有 {chosen_result['invalid_count']} 个非空值无法识别为重量，"
            "已按 0 处理。"
        )

    return {
        "include": True,
        "base_name": base_name,
        "numeric": chosen_result["numeric"],
        "display": chosen_result["display"],
        "warning": warning,
    }


def _is_summary_venue_name(value: object) -> bool:
    key = _normalize_header_key(value)
    if not key:
        return False
    return any(keyword in key for keyword in _SUMMARY_ROW_KEYWORDS)


def _build_display_df_from_numeric(
    numeric_df: pd.DataFrame,
    base_names: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    material_cols = _get_material_display_columns(base_names)

    for _, row in numeric_df.iterrows():
        entry = {VENUE_COL: _normalize_text(row.get(VENUE_COL, ""))}
        for col in material_cols:
            entry[col] = _format_numeric_display(float(row.get(col, 0) or 0))
        rows.append(entry)

    return normalize_display_df(pd.DataFrame(rows), base_names)


def _collapse_material_rows(
    df: pd.DataFrame,
    base_names: list[str],
    venue_names: list[str] | None = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return normalize_df(pd.DataFrame(columns=[VENUE_COL]), base_names)

    material_cols = _get_material_display_columns(base_names)
    clean = normalize_df(df, base_names)
    work = clean[[VENUE_COL] + material_cols].copy()
    work[VENUE_COL] = work[VENUE_COL].astype(str).str.strip()
    work = work[work[VENUE_COL] != ""].copy()
    work = work[~work[VENUE_COL].apply(_is_summary_venue_name)].copy()
    if work.empty:
        return normalize_df(pd.DataFrame(columns=[VENUE_COL]), base_names)

    work["__venue_key"] = work[VENUE_COL].map(normalize_name)
    work = work[work["__venue_key"] != ""].copy()
    if work.empty:
        return normalize_df(pd.DataFrame(columns=[VENUE_COL]), base_names)

    if venue_names:
        display_name_map = {normalize_name(name): name for name in venue_names}
        work = work[work["__venue_key"].isin(display_name_map)].copy()
        if work.empty:
            return normalize_df(pd.DataFrame(columns=[VENUE_COL]), base_names)
    else:
        display_name_map = (
            work.drop_duplicates("__venue_key")
            .set_index("__venue_key")[VENUE_COL]
            .to_dict()
        )

    grouped = work.groupby("__venue_key", sort=False)[material_cols].sum().reset_index()
    grouped[VENUE_COL] = grouped["__venue_key"].map(display_name_map)
    grouped = grouped[[VENUE_COL] + material_cols]
    return normalize_df(grouped, base_names)


def _get_upload_stats(df: pd.DataFrame, venue_names: list[str]) -> tuple[int, int]:
    if df is None or df.empty:
        return 0, 0

    work = df[[VENUE_COL]].copy()
    work[VENUE_COL] = work[VENUE_COL].astype(str).str.strip()
    work = work[work[VENUE_COL] != ""].copy()
    work = work[~work[VENUE_COL].apply(_is_summary_venue_name)].copy()
    if work.empty:
        return 0, 0

    work["__venue_key"] = work[VENUE_COL].map(normalize_name)
    work = work[work["__venue_key"] != ""].copy()
    duplicate_venue_count = max(len(work) - work["__venue_key"].nunique(), 0)

    unknown_venue_count = 0
    if venue_names:
        known_keys = {normalize_name(name) for name in venue_names}
        unknown_venue_count = int((~work["__venue_key"].isin(known_keys)).sum())

    return duplicate_venue_count, unknown_venue_count


def _empty_upload_result(error: str) -> MaterialUploadResult:
    return MaterialUploadResult(
        numeric_df=pd.DataFrame(columns=["序号", VENUE_COL, TOTAL_COL]),
        display_df=pd.DataFrame(columns=[VENUE_COL]),
        material_columns=[],
        warnings=[],
        stats={
            "matched_venue_count": 0,
            "ignored_column_count": 0,
            "unknown_venue_count": 0,
            "duplicate_venue_count": 0,
        },
        error=error,
    )


def _process_material_upload(df_raw: pd.DataFrame, venue_names: list[str]) -> MaterialUploadResult:
    venue_col = _find_venue_column(df_raw.columns)
    if venue_col is None:
        return _empty_upload_result(
            "未能识别场馆名称列，请确保文件中包含“场馆名称”或类似字段。"
        )

    non_material_keywords = {
        "序号", "备注", "编号", "no", "remark", "note", "index",
        "场馆名称", "场馆名", "场馆", "名称", "venue", "venue_name", "name",
        "地址", "详细地址", "address", "场馆地址", "addr", "位置",
        "承办项目", "项目", "运动项目", "sport", "project", "event",
        "经度", "lng", "longitude", "lon",
        "纬度", "lat", "latitude",
        "联系人", "联系电话", "联系", "contact", "phone", "tel", "mobile",
        "需求量", "需求", "需求量_kg", "demand", "weight", "重量", "weight_kg",
        "合计", "总计", "总需求", "total", "小计", "subtotal", "sum",
    }

    material_cols: list[str] = []
    ignored_columns: list[str] = []
    for col in df_raw.columns:
        if col == venue_col:
            continue
        col_lower = str(col).strip().lower()
        is_non_material = any(keyword in col_lower for keyword in non_material_keywords)
        if not is_non_material:
            material_cols.append(col)
        elif df_raw[col].notna().any():
            ignored_columns.append(f"已忽略列“{_normalize_text(col)}”。")

    if not material_cols:
        for col in df_raw.columns:
            if col == venue_col:
                continue
            if pd.to_numeric(df_raw[col], errors="coerce").notna().any():
                material_cols.append(col)

    if not material_cols:
        return _empty_upload_result("未识别到有效的物资列，请检查文件中是否包含物资分类和重量数据。")

    for col in material_cols:
        df_raw[col] = df_raw[col].apply(_parse_weight_to_kg)

    df_raw[TOTAL_COL] = df_raw[material_cols].sum(axis=1).round(_WEIGHT_ROUND_DECIMALS)
    df_raw = df_raw[df_raw[venue_col].notna() & (df_raw[venue_col].astype(str).str.strip() != "")]
    df_raw = df_raw[df_raw[venue_col].astype(str).str.lower() != "nan"]
    df_raw = df_raw.reset_index(drop=True)

    if df_raw.empty:
        return _empty_upload_result("上传文件中没有有效的场馆物资数据行。")

    base_names = [_material_col_to_base_name(str(col).strip()) or str(col).strip() for col in material_cols]
    material_data: dict[str, pd.Series] = {}
    for idx, col in enumerate(material_cols):
        display_col = _format_material_display_name(base_names[idx])
        material_data[display_col] = df_raw[col].round(2).values

    numeric_df = pd.DataFrame(
        {
            "序号": range(1, len(df_raw) + 1),
            VENUE_COL: df_raw[venue_col].astype(str).str.strip().values,
            **material_data,
            TOTAL_COL: df_raw[TOTAL_COL].round(2).values,
        }
    )
    duplicate_venue_count, unknown_venue_count = _get_upload_stats(numeric_df, venue_names)
    numeric_df = _collapse_material_rows(numeric_df, base_names, venue_names)
    display_df = _build_display_df_from_numeric(numeric_df, base_names)

    return MaterialUploadResult(
        numeric_df=numeric_df,
        display_df=display_df,
        material_columns=base_names,
        warnings=ignored_columns,
        stats={
            "matched_venue_count": len(numeric_df),
            "ignored_column_count": len(ignored_columns),
            "unknown_venue_count": unknown_venue_count,
            "duplicate_venue_count": duplicate_venue_count,
        },
    )


def _filter_to_known_venues(df: pd.DataFrame, venue_names: list[str]) -> pd.DataFrame:
    if df.empty:
        return df

    venue_key_map = {normalize_name(name): name for name in venue_names}
    filtered = df.copy()
    filtered["__venue_key"] = filtered[VENUE_COL].astype(str).str.strip().map(normalize_name)
    filtered = filtered[filtered["__venue_key"].isin(venue_key_map)].copy()
    if filtered.empty:
        return filtered.drop(columns="__venue_key", errors="ignore")

    filtered[VENUE_COL] = filtered["__venue_key"].map(venue_key_map)
    filtered = filtered.drop(columns="__venue_key")
    return filtered.reset_index(drop=True)


def sync_from_df(df: pd.DataFrame, display_df: pd.DataFrame | None = None) -> None:
    base_names = _collect_material_base_names(df, display_df)
    venue_names = [venue.get("name", "") for venue in st.session_state.get("venues", [])]
    clean = _collapse_material_rows(df, base_names, venue_names)
    clean_display = _build_display_df_from_numeric(clean, base_names)

    st.session_state.demands_df = clean.copy()
    st.session_state.demands_display_df = clean_display.copy()

    demands_norm: dict[str, dict[str, float]] = {}
    material_demands: dict[str, dict[str, dict[str, dict[str, float | str]]]] = {}
    material_cols = _get_material_display_columns(base_names)

    for _, row in clean.iterrows():
        venue_display = str(row[VENUE_COL]).strip()
        venue_key = normalize_name(venue_display)
        values = [_round_weight(row.get(col, 0)) for col in material_cols]
        data = {base_names[idx]: values[idx] for idx in range(len(base_names))}
        data["总需求"] = sum(values)

        if venue_key:
            demands_norm[venue_key] = data

        for idx, col in enumerate(material_cols):
            weight = _round_weight(row.get(col, 0))
            if weight > 0:
                material_demands.setdefault(venue_display, {})
                material_demands[venue_display].setdefault(base_names[idx], {})
                material_demands[venue_display][base_names[idx]]["总计"] = {
                    "weight_kg": weight,
                    "volume_m3": 0.0,
                    "urgency": "中",
                }

    st.session_state.demands = demands_norm
    st.session_state.material_demands = material_demands
    st.session_state.material_columns = base_names


def build_online_df(venue_names: list[str]) -> pd.DataFrame:
    base_names = _collect_material_base_names()
    material_cols = _get_material_display_columns(base_names)

    if st.session_state.get("demands_df") is not None:
        df = normalize_df(st.session_state.demands_df, base_names)
        existing = set(df[VENUE_COL].astype(str).tolist())
        for venue_name in venue_names:
            if venue_name not in existing:
                df = pd.concat(
                    [df, pd.DataFrame([{VENUE_COL: venue_name, **{col: 0.0 for col in material_cols}}])],
                    ignore_index=True,
                )
        df = df[df[VENUE_COL].isin(venue_names)].reset_index(drop=True)
    else:
        df = build_empty_df(venue_names, base_names)

    if st.session_state.get("material_demands"):
        for venue, categories in st.session_state.material_demands.items():
            if venue in venue_names:
                mask = df[VENUE_COL] == venue
                for category, materials in categories.items():
                    col_name = _format_material_display_name(category)
                    if col_name and col_name in df.columns:
                        total = _sum_weight_values(
                            [item.get("weight_kg", 0) for item in materials.values()]
                        )
                        df.loc[mask, col_name] = total

    return normalize_df(df, base_names)


def build_online_display_df(venue_names: list[str]) -> pd.DataFrame:
    base_names = _collect_material_base_names()
    material_cols = _get_material_display_columns(base_names)
    display_state = st.session_state.get("demands_display_df")

    if isinstance(display_state, pd.DataFrame):
        df = normalize_display_df(display_state, base_names)
        existing = set(df[VENUE_COL].astype(str).tolist())
        for venue_name in venue_names:
            if venue_name not in existing:
                df = pd.concat(
                    [df, pd.DataFrame([{VENUE_COL: venue_name, **{col: "0" for col in material_cols}}])],
                    ignore_index=True,
                )
        df = df[df[VENUE_COL].isin(venue_names)].reset_index(drop=True)
        return normalize_display_df(df, base_names)

    return normalize_display_df(build_online_df(venue_names), base_names)


def merge_upload_data(
    df_cleaned: pd.DataFrame,
    material_columns: list[str],
    venue_names: list[str],
    display_df: pd.DataFrame | None = None,
) -> None:
    current_state_df = st.session_state.get("demands_df")
    current_display_state = st.session_state.get("demands_display_df")
    base_names = _collect_material_base_names(current_state_df, current_display_state, df_cleaned)
    if material_columns:
        base_names = _collect_material_base_names(
            pd.DataFrame(columns=_get_material_display_columns(material_columns)),
            current_state_df,
            current_display_state,
            df_cleaned,
        )
    st.session_state.material_columns = base_names

    merged_numeric_df = normalize_df(build_online_df(venue_names), base_names)
    merged_display_df = normalize_display_df(build_online_display_df(venue_names), base_names)
    upload_numeric_df = normalize_df(df_cleaned, base_names)
    upload_display_df = (
        normalize_display_df(display_df, base_names)
        if display_df is not None
        else _build_display_df_from_numeric(upload_numeric_df, base_names)
    )

    dynamic_material_cols = _get_material_display_columns(base_names)
    merged_numeric_df = merged_numeric_df[[VENUE_COL] + dynamic_material_cols].copy()
    merged_display_df = merged_display_df[[VENUE_COL] + dynamic_material_cols].copy()
    upload_cols = _get_material_display_columns(material_columns or base_names)

    for row_idx, row in upload_numeric_df.iterrows():
        venue_display = str(row[VENUE_COL]).strip()
        if not venue_display:
            continue

        mask = merged_numeric_df[VENUE_COL] == venue_display
        if not mask.any():
            merged_numeric_df = pd.concat(
                [merged_numeric_df, pd.DataFrame([{VENUE_COL: venue_display, **{col: 0.0 for col in dynamic_material_cols}}])],
                ignore_index=True,
            )
            merged_display_df = pd.concat(
                [merged_display_df, pd.DataFrame([{VENUE_COL: venue_display, **{col: "0" for col in dynamic_material_cols}}])],
                ignore_index=True,
            )
            mask = merged_numeric_df[VENUE_COL] == venue_display

        display_mask = merged_display_df[VENUE_COL] == venue_display
        source_display_row = upload_display_df.iloc[row_idx] if row_idx in upload_display_df.index else None

        for col in upload_cols:
            if col not in merged_numeric_df.columns:
                merged_numeric_df[col] = 0.0
                merged_display_df[col] = "0"
            merged_numeric_df.loc[mask, col] = float(row.get(col, 0) or 0)
            merged_display_df.loc[display_mask, col] = _normalize_display_value(
                source_display_row.get(col, row.get(col, 0))
                if source_display_row is not None
                else row.get(col, 0)
            )

    sync_from_df(merged_numeric_df, merged_display_df)


def build_saved_summary_df(venue_names: list[str]) -> pd.DataFrame:
    demands = st.session_state.get("demands") or {}
    if not demands:
        return pd.DataFrame(columns=[VENUE_COL, TOTAL_COL])

    venue_key_map = {normalize_name(name): name for name in venue_names}
    material_columns = _collect_material_base_names()

    rows: list[dict[str, float | str]] = []
    for venue_key, value in demands.items():
        display_name = venue_key_map.get(normalize_name(str(venue_key)), str(venue_key))
        if isinstance(value, dict):
            row: dict[str, float | str] = {VENUE_COL: display_name}
            subtotal = 0.0
            for material_name in material_columns:
                amount = _round_weight(value.get(material_name, 0))
                row[_format_material_display_name(material_name)] = amount
                subtotal = _sum_weight_values([subtotal, amount])
            row[TOTAL_COL] = float(value.get("总需求", subtotal) or 0)
        else:
            row = {VENUE_COL: display_name, TOTAL_COL: _round_weight(value)}
        rows.append(row)

    summary_df = pd.DataFrame(rows)
    if not summary_df.empty:
        numeric_cols = [col for col in summary_df.columns if col != VENUE_COL]
        for col in numeric_cols:
            summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").fillna(0.0).round(_WEIGHT_ROUND_DECIMALS)
    if TOTAL_COL not in summary_df.columns:
        summary_df[TOTAL_COL] = 0.0
    return summary_df


st.set_page_config(page_title="物资需求", page_icon="", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()
init_state()

venue_names = [venue["name"] for venue in st.session_state.get("venues", [])]
render_top_nav(
    tabs=[("在线填写", "sec-online"), ("上传文件", "sec-upload")],
    active_idx=0 if not venue_names else 1,
)

st.markdown(
    """
    <style>
    .glp-venue-card,
    .st-key-materials-upload-card,
    .st-key-materials-online-card {
        background: linear-gradient(135deg, rgba(223, 239, 188, 0.94) 0%, rgba(214, 234, 174, 0.92) 100%);
        border: 1px solid #d0e2b4;
        border-radius: 28px;
        padding: 1.6rem 1.75rem 1.65rem;
        box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
        margin-top: 1.2rem;
        overflow: hidden;
    }
    .glp-material-card-title {
        font-size: 1.9rem;
        font-weight: 700;
        color: #111111;
        margin-bottom: 1rem;
    }
    .glp-empty-banner {
        background: rgba(255, 250, 228, 0.86);
        color: #b19b63;
        border-radius: 20px;
        padding: 1.55rem 2rem;
        text-align: center;
        font-size: 1.3rem;
        margin-top: 3.6rem;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.45);
    }
    .glp-info-panel {
        background: #d8e4f4;
        color: #6b92bf;
        border-radius: 20px;
        padding: 1.45rem 1.65rem;
        font-size: 1.05rem;
        line-height: 1.95;
        margin-bottom: 1rem;
    }
    .glp-upload-note {
        color: #707070;
        font-size: 0.95rem;
        margin-top: 0.45rem;
    }
    .glp-success-band {
        margin: 0.95rem -1.75rem 0.85rem;
        padding: 0.95rem 1.75rem;
        background: #c3e86c;
        color: #111111;
        font-size: 1.15rem;
        font-weight: 600;
    }
    .glp-bottom-next {
        margin: 2.4rem auto 0;
        width: fit-content;
        font-size: 2rem;
    }
    .glp-bottom-next a {
        color: #111111;
        text-decoration: none;
        border-bottom: 1px solid #111111;
        padding: 0 1.2rem 0.2rem;
    }
    .glp-inline-label {
        color: #8a8a8a;
        font-size: 0.95rem;
        margin: 0 0 0.35rem 0;
    }
    div[data-testid="stFileUploader"] > label,
    div[data-testid="stTextInput"] > label,
    div[data-testid="stNumberInput"] > label {
        color: #1d2812 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stFileUploaderDropzone"] {
        background: rgba(255, 255, 255, 0.08) !important;
        border: 4px dashed #111111 !important;
        border-radius: 18px !important;
        min-height: 118px !important;
    }
    div[data-testid="stFileUploaderDropzone"] section {
        padding: 1rem !important;
    }
    div[data-testid="stFileUploaderDropzoneInstructions"] > div:first-child,
    div[data-testid="stFileUploaderDropzoneInstructions"] > small {
        display: none !important;
    }
    div[data-testid="stFileUploaderDropzone"] button {
        background: #ffffff !important;
        color: #111111 !important;
        border: 0 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
        font-size: 1rem !important;
        padding: 0.55rem 1.3rem !important;
    }
    div[data-testid="stAlert"] {
        border-radius: 0 !important;
        border: 0 !important;
    }
    div[data-testid="stDataFrame"],
    div[data-testid="stDataEditor"] {
        background: #ffffff !important;
        border-radius: 0 !important;
        overflow: hidden !important;
    }
    div[data-testid="stDataEditor"] [data-testid="StyledDataFrameDataCell"],
    div[data-testid="stDataEditor"] [data-testid="StyledDataFrameDataCell"] div,
    div[data-testid="stDataEditor"] [data-testid="StyledDataFrameHeaderCell"],
    div[data-testid="stDataEditor"] [data-testid="StyledDataFrameHeaderCell"] div {
        text-align: center !important;
        justify-content: center !important;
    }
    div[data-testid="stMetric"] {
        background: transparent !important;
        border: 0 !important;
        padding: 0.1rem 0 !important;
    }
    div[data-testid="stMetric"] label {
        color: #111111 !important;
        font-size: 1.02rem !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetricValue"] {
        color: #111111 !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
    }
    .stButton > button,
    .stDownloadButton > button {
        height: 3rem !important;
        border-radius: 12px !important;
        font-size: 1.12rem !important;
        border: 0 !important;
        box-shadow: 0 5px 13px rgba(0, 0, 0, 0.2) !important;
    }
    .stButton > button[kind="primary"] {
        background: #2cb46d !important;
        color: #ffffff !important;
    }
    .stButton > button:not([kind="primary"]),
    .stDownloadButton > button {
        background: #ffffff !important;
        color: #111111 !important;
    }
    .glp-template-wrap .stDownloadButton > button {
        width: 100% !important;
        justify-content: flex-start !important;
        padding-left: 1rem !important;
        font-size: 1rem !important;
    }
    .st-key-materials-upload-card .stDownloadButton > button {
        width: 100% !important;
        justify-content: flex-start !important;
        padding-left: 1rem !important;
        font-size: 1rem !important;
    }
    .glp-material-section-gap {
        height: 1.7rem;
    }
    .glp-bottom-nav {
        display: none !important;
    }
    @media (max-width: 900px) {
        .glp-venue-card,
        .st-key-materials-upload-card,
        .st-key-materials-online-card {
            padding: 1.2rem 1rem 1.35rem;
        }
        .glp-success-band {
            margin-left: -1rem;
            margin-right: -1rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

render_title("物资需求", "为各场馆录入物资配送需求，数据将用于 VRP 路径优化。")

if not venue_names:
    st.markdown(
        """
        <div class="glp-empty-banner">
            请先在【场馆录入】页面添加场馆后再录入物资需求
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_page_nav("pages/2_venues.py", "pages/4_vehicles.py", key_prefix="materials-nav")
    st.stop()


with st.container(key="materials-upload-card"):
    anchor("sec-upload")
    st.markdown(
        '<div class="glp-material-card-title">上传文件导入物资需求</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="glp-info-panel">
            <b>支持格式:</b>&nbsp;&nbsp;CSV/Excel(xlsx/xls)/TXT/JSON<br/>
            <b>智能处理:</b>&nbsp;&nbsp;自动跳过标题行、定位真实表头、识别物资列、过滤合计列，并统一换算为 kg
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "上传物资需求文件",
        type=["csv", "xlsx", "xls", "txt", "json"],
        label_visibility="collapsed",
    )
    st.markdown(
        '<div class="glp-upload-note">支持格式：CSV/Excel/TXT/JSON</div>',
        unsafe_allow_html=True,
    )

    mapped_df: pd.DataFrame | None = None
    upload_material_columns: list[str] = []
    mapped_display_df: pd.DataFrame | None = None

    if uploaded is not None:
        source_df, upload_error = _smart_read_excel(uploaded)
        if upload_error:
            st.error(upload_error)
        elif source_df is None or source_df.empty:
            st.warning("文件中没有可读取的数据")
        else:
            upload_result = _process_material_upload(source_df.copy(), venue_names)
            if upload_result.error:
                st.error(upload_result.error)
            else:
                mapped_df = upload_result.numeric_df
                upload_material_columns = upload_result.material_columns
                mapped_display_df = upload_result.display_df

                st.markdown('<div class="glp-success-band">成功读取</div>', unsafe_allow_html=True)
                st.markdown(
                    '<div class="glp-material-card-title" style="margin-top:0.15rem;">智能清洗结果</div>',
                    unsafe_allow_html=True,
                )

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("场馆数", upload_result.stats.get("matched_venue_count", 0))
                with col2:
                    st.metric("换算总需求量", f"{mapped_df[TOTAL_COL].sum():,.0f} kg")
                with col3:
                    st.metric("忽略列数", upload_result.stats.get("ignored_column_count", 0))
                with col4:
                    st.metric("未知场馆数", upload_result.stats.get("unknown_venue_count", 0))

                duplicate_count = upload_result.stats.get("duplicate_venue_count", 0)
                if duplicate_count > 0:
                    st.info(f"本次上传中检测到 {duplicate_count} 行重复场馆数据，确认合并后将以后出现的同场馆记录为准。")

                unknown_count = upload_result.stats.get("unknown_venue_count", 0)
                if unknown_count > 0:
                    st.info(f"本次上传中有 {unknown_count} 条记录的场馆名称未在当前场馆列表中出现，请合并前自行确认。")

                if upload_result.warnings:
                    for message in upload_result.warnings:
                        st.warning(message)

                st.markdown('<div class="glp-inline-label">已识别</div>', unsafe_allow_html=True)
                st.dataframe(_style_display_df(mapped_df), hide_index=True, width="stretch", height=290)

                if st.button("确认合并到需求列表", type="primary", key="merge-upload"):
                    merge_upload_data(mapped_df, upload_material_columns, venue_names, mapped_display_df)
                    st.success("已合并并保存上传数据")

    st.markdown('<div class="glp-material-section-gap"></div>', unsafe_allow_html=True)
    st.markdown('<div class="glp-material-card-title">下载导入模板</div>', unsafe_allow_html=True)
    template = pd.DataFrame(
        {
            VENUE_COL: ["主体场馆", "游泳中心", "运动员村"],
            WEIGHT_COLS[0]: [500, 700, 300],
            WEIGHT_COLS[1]: [300, 400, 200],
            WEIGHT_COLS[2]: [100, 100, 150],
            WEIGHT_COLS[3]: [200, 250, 120],
            WEIGHT_COLS[4]: [150, 180, 90],
        }
    )
    st.download_button(
        "下载 CSV 模板",
        template.to_csv(index=False).encode("utf-8-sig"),
        "material_template.csv",
        "text/csv",
        width="stretch",
    )


with st.container(key="materials-online-card"):
    anchor("sec-online")
    st.markdown('<div class="glp-material-card-title">在线填写</div>', unsafe_allow_html=True)

    base_df = build_online_display_df(venue_names)
    base_names = _collect_material_base_names(base_df)
    material_display_cols = [col for col in base_df.columns if col != VENUE_COL]

    edited = st.data_editor(
        base_df[[VENUE_COL] + material_display_cols],
        disabled=[VENUE_COL],
        width="stretch",
        hide_index=True,
        column_config={
            VENUE_COL: st.column_config.TextColumn("场馆名称", disabled=True, alignment="left"),
            **{col: st.column_config.TextColumn(col) for col in material_display_cols},
        },
    )
    preview_numeric_df, _, _ = parse_online_editor_df(edited, base_names, strict=False)
    edited[TOTAL_COL] = (
        preview_numeric_df[material_display_cols].sum(axis=1).round(_WEIGHT_ROUND_DECIMALS)
        if material_display_cols else 0.0
    )

    metric_items = [
        (_material_col_to_base_name(col), f"{preview_numeric_df[col].sum():,.3f}kg")
        for col in material_display_cols
    ]
    metric_items.append(("总计", f"{preview_numeric_df[TOTAL_COL].sum():,.3f}kg"))
    for start in range(0, len(metric_items), 4):
        row_items = metric_items[start:start + 4]
        metric_cols = st.columns(len(row_items))
        for idx, (label, value) in enumerate(row_items):
            with metric_cols[idx]:
                st.metric(label, value)

    if st.button("保存在线填写数据", type="primary", width="stretch"):
        saved_numeric_df, saved_display_df, save_errors = parse_online_editor_df(edited, base_names, strict=True)
        if save_errors:
            st.error("\n".join(save_errors[:3]))
        else:
            sync_from_df(saved_numeric_df, saved_display_df)
            st.success("在线填写数据已保存")

    st.markdown('<div class="glp-material-section-gap"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glp-material-card-title">当前已保存的物资需求数据</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.demands:
        summary_df = build_saved_summary_df(venue_names)
        venue_count = len(summary_df) if not summary_df.empty else len(st.session_state.demands)
        total = float(summary_df[TOTAL_COL].sum()) if TOTAL_COL in summary_df.columns else 0.0
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("场馆数", venue_count)
        with m2:
            st.metric("总物资需求量", f"{total:,.0f}kg")
        with m3:
            st.metric("场均需求", f"{(total / venue_count if venue_count else 0):,.0f}kg")
        if not summary_df.empty:
            st.dataframe(_style_display_df(summary_df), hide_index=True, width="stretch", height=280)
    else:
        st.info("暂无物资需求数据")

render_page_nav("pages/2_venues.py", "pages/4_vehicles.py", key_prefix="materials-nav")
