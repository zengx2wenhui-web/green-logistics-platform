"""物资需求页面"""
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

# ========== 上传文件 ==========
with tab2:
    st.subheader("上传文件导入物资需求")
    st.info("**支持格式：** CSV / Excel / TXT / JSON | **必需列：** 场馆名称 + 各物资类别重量")

    uploaded_file = st.file_uploader(
        "上传物资需求文件",
        type=["csv", "xlsx", "xls", "txt", "json"],
    )

    if uploaded_file:
        df_upload, error = read_uploaded_file(uploaded_file)
        if error:
            st.error(f" {error}")
        elif df_upload is not None and len(df_upload) > 0:
            st.success(f" 成功读取 {len(df_upload)} 条数据")
            st.dataframe(df_upload, use_container_width=True)

            columns = df_upload.columns.tolist()
            venue_col = None
            for col in columns:
                if "场馆" in str(col) or "名称" in str(col) or "name" in str(col).lower():
                    venue_col = venue_col or col

            if venue_col is None:
                venue_col = st.selectbox("选择【场馆名称】列", columns)

            weight_cols_map = {}
            for cat_key in WEIGHT_COLS:
                cat_lower = cat_key.lower().replace("(kg)", "").strip()
                matched = None
                for col in columns:
                    if cat_lower in str(col).lower() or cat_key.replace("(kg)", "") in str(col):
                        matched = col
                        break
                weight_cols_map[cat_key] = matched

            with st.expander(" 手动调整列映射"):
                venue_col = st.selectbox("场馆名称列", columns, index=columns.index(venue_col) if venue_col in columns else 0)
                for cat in WEIGHT_COLS:
                    options = [None] + [c for c in columns if c != venue_col]
                    current = weight_cols_map.get(cat)
                    idx = options.index(current) if current in options else 0
                    weight_cols_map[cat] = st.selectbox(f"{cat}列", options, index=idx)

            if st.button(" 确认并合并到数据表", type="primary"):
                upload_data = {"场馆名称": df_upload[venue_col].astype(str)}
                for cat, col in weight_cols_map.items():
                    upload_data[cat] = pd.to_numeric(df_upload[col], errors="coerce").fillna(0) if col else 0
                df_mapped = pd.DataFrame(upload_data)

                if st.session_state.get("demands_df") is not None:
                    df_main = st.session_state["demands_df"].copy()
                    for _, row in df_mapped.iterrows():
                        mask = df_main["场馆名称"] == row["场馆名称"]
                        if mask.any():
                            for cat in WEIGHT_COLS:
                                df_main.loc[mask, cat] = row[cat]
                        else:
                            df_main = pd.concat([df_main, row.to_frame().T], ignore_index=True)
                    st.session_state["demands_df"] = df_main
                else:
                    for col in WEIGHT_COLS:
                        if col not in df_mapped.columns:
                            df_mapped[col] = 0
                    st.session_state["demands_df"] = df_mapped

                st.success(f" 已合并 {len(df_mapped)} 条记录！")
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

st.caption(" 提示：物资需求数据将用于VRP路径优化中的车辆调度计算")