"""物资需求页面 - 动态导入与智能清洗"""
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from utils.file_reader import read_uploaded_file

st.set_page_config(page_title="物资需求", page_icon="")

st.title(" 第三步：物资需求录入")
st.markdown("为各场馆录入物资配送需求，数据将用于VRP路径优化")

# ===== 初始化 =====
if "demands_df" not in st.session_state:
    st.session_state["demands_df"] = None
if "demands" not in st.session_state:
    st.session_state["demands"] = {}

WEIGHT_COLS = ["通用赛事物资(kg)", "专项运动器材(kg)", "医疗物资(kg)", "IT设备(kg)"]

# ===================== 智能单位换算函数 =====================
# 排除列关键词（合计/总计/Total 等）
_EXCLUDE_COL_KEYWORDS = {"合计", "总计", "总需求", "total", "小计", "subtotal", "sum"}
# 排除列关键词（序号/备注）
_SKIP_COL_KEYWORDS = {"序号", "备注", "编号", "no", "remark", "note", "index"}


def _parse_weight_to_kg(value) -> float:
    """将带单位的字符串或纯数字统一换算为 kg 浮点数。

    支持：纯数字（默认 kg）、500g、2t、1.5吨、3千克、200斤、0.5T 等。
    """
    if pd.isna(value):
        return 0.0
    s = str(value).strip().replace(",", "").replace("，", "").replace(" ", "")
    if not s or s.lower() == "nan":
        return 0.0

    # 正则：提取 数字部分 + 可选单位
    m = re.match(
        r'^([+-]?\d+(?:\.\d+)?)\s*'
        r'(kg|千克|公斤|g|克|t|吨|ton|斤|lb|lbs|磅)?$',
        s, re.IGNORECASE,
    )
    if not m:
        # 尝试只提取数字
        num_match = re.search(r'([+-]?\d+(?:\.\d+)?)', s)
        if num_match:
            return float(num_match.group(1))
        return 0.0

    num = float(m.group(1))
    unit = (m.group(2) or "").lower()

    conversion = {
        "": 1.0, "kg": 1.0, "千克": 1.0, "公斤": 1.0,
        "g": 0.001, "克": 0.001,
        "t": 1000.0, "吨": 1000.0, "ton": 1000.0,
        "斤": 0.5,
        "lb": 0.4536, "lbs": 0.4536, "磅": 0.4536,
    }
    return num * conversion.get(unit, 1.0)


def _is_material_col(col_name: str) -> bool:
    """判断一个列名是否为物资分项列（排除场馆名称/序号/备注/合计等）。"""
    col_lower = str(col_name).strip().lower()
    # 排除合计类列
    for kw in _EXCLUDE_COL_KEYWORDS:
        if kw in col_lower:
            return False
    # 排除序号/备注类列
    for kw in _SKIP_COL_KEYWORDS:
        if kw in col_lower:
            return False
    # 排除场馆名称列本身
    if "场馆名称" in str(col_name):
        return False
    return True


def _smart_read_excel(uploaded_file) -> tuple:
    """智能读取 Excel/CSV，自动定位真实表头行。

    扫描前 20 行，以包含「场馆名称」关键字的行作为真实表头。
    返回 (DataFrame, error_msg)。
    """
    filename = uploaded_file.name.lower()
    uploaded_file.seek(0)

    # 先用 header=None 读取原始数据
    try:
        if filename.endswith((".xlsx", ".xls")):
            raw_df = pd.read_excel(uploaded_file, header=None, nrows=30)
        elif filename.endswith(".csv"):
            uploaded_file.seek(0)
            for enc in ("utf-8", "gbk", "gb2312", "utf-8-sig"):
                try:
                    uploaded_file.seek(0)
                    raw_df = pd.read_csv(uploaded_file, header=None, nrows=30, encoding=enc)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            else:
                return None, "无法识别文件编码"
        else:
            # 对其他格式降级到普通读取
            uploaded_file.seek(0)
            return read_uploaded_file(uploaded_file)
    except Exception as e:
        return None, f"文件读取失败: {e}"

    # 扫描前 20 行，找到包含"场馆名称"的行
    header_row_idx = None
    for idx in range(min(20, len(raw_df))):
        row_values = [str(v).strip() for v in raw_df.iloc[idx].values]
        for val in row_values:
            if "场馆名称" in val:
                header_row_idx = idx
                break
        if header_row_idx is not None:
            break

    if header_row_idx is None:
        # 没有找到"场馆名称"，退回到普通读取
        uploaded_file.seek(0)
        return read_uploaded_file(uploaded_file)

    # 用找到的行作为表头重新读取
    uploaded_file.seek(0)
    try:
        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file, header=header_row_idx)
        else:
            for enc in ("utf-8", "gbk", "gb2312", "utf-8-sig"):
                try:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, header=header_row_idx, encoding=enc)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
    except Exception as e:
        return None, f"使用检测到的表头重新读取失败: {e}"

    # 清理列名空白
    df.columns = [str(c).strip() for c in df.columns]
    # 去除全空行
    df = df.dropna(how="all").reset_index(drop=True)

    return df, None


def _process_material_upload(df_raw: pd.DataFrame) -> pd.DataFrame:
    """对上传的 DataFrame 执行智能清洗：

    1. 锁定「场馆名称」列
    2. 提取物资分项列（排除序号/备注/合计）
    3. 遍历分项列做单位换算 → kg
    4. 按行重新求和得到「总需求(kg)」
    5. 输出精简三列：序号、场馆名称、总需求(kg)
    """
    # 定位场馆名称列
    venue_col = None
    for col in df_raw.columns:
        if "场馆名称" in str(col):
            venue_col = col
            break
    if venue_col is None:
        # 退而求其次
        for col in df_raw.columns:
            cl = str(col).lower()
            if "场馆" in str(col) or "名称" in str(col) or "venue" in cl:
                venue_col = col
                break
    if venue_col is None:
        return pd.DataFrame(columns=["序号", "场馆名称", "总需求(kg)"])

    # 提取物资分项列
    material_cols = [c for c in df_raw.columns if c != venue_col and _is_material_col(c)]

    if not material_cols:
        # 如果没有识别到物资列，尝试把所有数值列当作物资列
        for c in df_raw.columns:
            if c == venue_col:
                continue
            if pd.to_numeric(df_raw[c], errors="coerce").notna().any():
                if _is_material_col(c):
                    material_cols.append(c)

    # 对物资分项列做单位换算
    for col in material_cols:
        df_raw[col] = df_raw[col].apply(_parse_weight_to_kg)

    # 按行求和（忽略原表旧合计列）
    df_raw["总需求(kg)"] = df_raw[material_cols].sum(axis=1)

    # 去除场馆名为空的行
    df_raw = df_raw[df_raw[venue_col].notna() & (df_raw[venue_col].astype(str).str.strip() != "")]
    # 去除场馆名为 nan 的行
    df_raw = df_raw[df_raw[venue_col].astype(str).str.lower() != "nan"]
    df_raw = df_raw.reset_index(drop=True)

    # 构建精简输出
    result = pd.DataFrame({
        "序号": range(1, len(df_raw) + 1),
        "场馆名称": df_raw[venue_col].astype(str).str.strip().values,
        "总需求(kg)": df_raw["总需求(kg)"].round(2).values,
    })
    return result

# ===== 检查场馆数据 =====
venue_names = []
if "venues" in st.session_state and st.session_state.venues:
    venue_names = [v["name"] for v in st.session_state.venues]

if not venue_names:
    st.warning(" 请先在【场馆录入】页面添加场馆后再录入物资需求")
    st.stop()

# ===== 主标签页 =====
tab1, tab2 = st.tabs([" 在线填写", " 上传文件"])

# ========== 在线填写 ==========
with tab1:
    st.subheader("在线填写物资需求")

    # 构建初始数据
    default_data = {
        "场馆名称": venue_names,
        **{col: [0] * len(venue_names) for col in WEIGHT_COLS},
    }

    # 恢复已保存数据
    if st.session_state.get("demands_df") is not None:
        df = st.session_state["demands_df"].copy()
        existing = set(df["场馆名称"].tolist())
        for vn in venue_names:
            if vn not in existing:
                new_row = {"场馆名称": vn, **{col: 0 for col in WEIGHT_COLS}}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df = df[df["场馆名称"].isin(venue_names)]
    else:
        df = pd.DataFrame(default_data)

    # 恢复 material_demands 历史数据
    if st.session_state.get("material_demands"):
        col_map = {
            "通用赛事物资": "通用赛事物资(kg)",
            "专项运动器材": "专项运动器材(kg)",
            "医疗物资": "医疗物资(kg)",
            "IT设备": "IT设备(kg)",
        }
        for venue, categories in st.session_state.material_demands.items():
            if venue in venue_names:
                mask = df["场馆名称"] == venue
                for cat, materials in categories.items():
                    col_name = col_map.get(cat)
                    if col_name and col_name in df.columns:
                        total = sum(m.get("weight_kg", 0) for m in materials.values())
                        df.loc[mask, col_name] = total

    # 可编辑表格
    edited_df = st.data_editor(
        df,
        disabled=["场馆名称"],
        num_rows="fixed",
        use_container_width=True,
        column_config={col: st.column_config.NumberColumn(min_value=0, step=10, default=0) for col in WEIGHT_COLS},
    )
    edited_df["总需求(kg)"] = edited_df[WEIGHT_COLS].sum(axis=1)

    # 各列合计
    st.markdown("---")
    st.subheader(" 各列合计")
    cols = st.columns(5)
    labels = WEIGHT_COLS + ["总计"]
    values = [edited_df[col].sum() for col in WEIGHT_COLS] + [edited_df["总需求(kg)"].sum()]
    for i, (label, val) in enumerate(zip(labels, values)):
        with cols[i]:
            st.metric(label.replace("(kg)", ""), f"{val:,.0f} kg")

    st.markdown("---")

    # 保存按钮
    if st.button(" 保存物资需求", type="primary", use_container_width=True):
        st.session_state["demands_df"] = edited_df.copy()

        # 同步保存 demands 字典
        demands = {}
        for _, row in edited_df.iterrows():
            venue = row["场馆名称"]
            general = float(row.get("通用赛事物资(kg)", 0) or 0)
            sports = float(row.get("专项运动器材(kg)", 0) or 0)
            medical = float(row.get("医疗物资(kg)", 0) or 0)
            it_equip = float(row.get("IT设备(kg)", 0) or 0)
            demands[venue] = {
                "通用赛事物资": general, "专项运动器材": sports,
                "医疗物资": medical, "IT设备": it_equip,
                "总需求": general + sports + medical + it_equip,
            }
        st.session_state["demands"] = demands

        # 同步 material_demands
        st.session_state.material_demands = {}
        for _, row in edited_df.iterrows():
            venue = row["场馆名称"]
            for col in WEIGHT_COLS:
                cat_name = col.replace("(kg)", "")
                weight = float(row[col] or 0)
                if weight > 0:
                    st.session_state.material_demands.setdefault(venue, {})
                    st.session_state.material_demands[venue].setdefault(cat_name, {})
                    st.session_state.material_demands[venue][cat_name]["总计"] = {
                        "weight_kg": weight, "volume_m3": 0, "urgency": "中",
                    }

        st.success(f" 已保存 {len(demands)} 个场馆的物资需求，总量 {edited_df['总需求(kg)'].sum():,.0f} kg")

    with st.expander(" 预览完整数据"):
        st.dataframe(edited_df, hide_index=True, use_container_width=True)

# ========== 上传文件（智能导入） ==========
with tab2:
    st.subheader("上传文件导入物资需求")
    st.info(
        "**支持格式：** CSV / Excel (.xlsx/.xls) / TXT / JSON\n\n"
        "**智能处理：** 自动跳过表头大标题，定位「场馆名称」行，"
        "自动识别物资分项列，排除合计/总计列，统一换算为 kg。"
    )

    uploaded_file = st.file_uploader(
        "上传物资需求文件",
        type=["csv", "xlsx", "xls", "txt", "json"],
    )

    if uploaded_file:
        with st.spinner("正在智能解析文件..."):
            df_upload, error = _smart_read_excel(uploaded_file)

        if error:
            st.error(f" {error}")
        elif df_upload is not None and len(df_upload) > 0:
            st.success(f" 成功读取 {len(df_upload)} 条数据（已自动定位表头）")

            with st.expander(" 查看原始读取数据", expanded=False):
                st.dataframe(df_upload, use_container_width=True)

            # 智能清洗 & 单位换算
            df_cleaned = _process_material_upload(df_upload.copy())

            if df_cleaned.empty:
                st.warning(" 未能从文件中提取到有效的物资需求数据，请检查文件是否包含「场馆名称」列。")
            else:
                st.markdown("####  智能清洗结果")
                st.markdown(
                    f"已识别 **{len(df_cleaned)}** 个场馆，自动排除合计/总计行，"
                    f"所有数值已统一换算为 **kg**。"
                )
                st.dataframe(df_cleaned, hide_index=True, use_container_width=True)

                total_kg = df_cleaned["总需求(kg)"].sum()
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    st.metric("场馆数", len(df_cleaned))
                with col_s2:
                    st.metric("重算总需求", f"{total_kg:,.2f} kg")

                if st.button(" 确认并合并到需求表", type="primary", use_container_width=True):
                    # 合并到 demands 字典
                    for _, row in df_cleaned.iterrows():
                        venue_name = str(row["场馆名称"]).strip()
                        total_demand = float(row["总需求(kg)"])
                        if venue_name:
                            st.session_state["demands"][venue_name] = {
                                "总需求": total_demand,
                            }
                    st.success(f" 已合并 {len(df_cleaned)} 条记录到需求表！总需求 {total_kg:,.2f} kg")
                    st.rerun()

    # 模板下载
    st.markdown("---")
    st.subheader(" 下载导入模板")
    template = pd.DataFrame({
        "场馆名称": ["主体育场", "游泳中心", "运动员村"],
        "通用赛事物资(kg)": [500, 1000, 300],
        "专项运动器材(kg)": [300, 500, 200],
        "医疗物资(kg)": [100, 200, 150],
        "IT设备(kg)": [200, 300, 100],
    })
    st.download_button("下载CSV模板", data=template.to_csv(index=False),
                       file_name="material_demand_template.csv", mime="text/csv")

# ========== 底部摘要 ==========
st.markdown("---")
st.subheader(" 当前已保存的物资需求数据")

if st.session_state.get("demands") and len(st.session_state["demands"]) > 0:
    demands = st.session_state["demands"]
    total = sum(v.get("总需求", 0) if isinstance(v, dict) else v for v in demands.values())

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("场馆数", len(demands))
    with col_m2:
        st.metric("总物资需求量", f"{total:,.0f} kg")
    with col_m3:
        avg = total / len(demands) if demands else 0
        st.metric("场均需求", f"{avg:,.0f} kg")

    summary_list = [{"场馆": k, "总需求(kg)": v.get("总需求", 0) if isinstance(v, dict) else v} for k, v in demands.items()]
    st.dataframe(pd.DataFrame(summary_list), hide_index=True, use_container_width=True)
    st.success(" 数据已同步，可供路径优化页面使用")
else:
    st.warning(" 暂无物资需求数据")

st.markdown("---")
if st.button("下一步：车辆配置 ➡️", type="primary", use_container_width=True):
    st.switch_page("pages/4_车辆配置.py")

st.caption(" 提示：物资需求数据将用于VRP路径优化中的车辆调度计算")