"""物资需求页面"""
import streamlit as st
import pandas as pd
import plotly.express as px
from utils.file_reader import read_uploaded_file

st.set_page_config(page_title="物资需求", page_icon="📦")

st.title("📦 物资需求录入")
st.markdown("为各场馆录入物资配送需求，数据将用于VRP路径优化")

# ===== 初始化 session_state =====
if "demands_df" not in st.session_state:
    st.session_state["demands_df"] = None

if "demands" not in st.session_state:
    st.session_state["demands"] = {}

# ===== 预置4种物资类别 =====
MATERIAL_CATEGORIES = {
    "通用赛事物资": 0,
    "专项运动器材": 0,
    "医疗物资": 0,
    "IT设备": 0
}
WEIGHT_COLS = ["通用赛事物资(kg)", "专项运动器材(kg)", "医疗物资(kg)", "IT设备(kg)"]

# ===== 检查场馆数据 =====
venue_names = []
if "venues" in st.session_state and st.session_state.venues:
    venue_names = [v["name"] for v in st.session_state.venues]

if not venue_names:
    st.warning("⚠️ 请先在【场馆录入】页面添加场馆后再录入物资需求")
    st.info("**物资需求文件格式：** 场馆名称、各类别物资重量")
    st.stop()

# ===== 主标签页 =====
tab1, tab2 = st.tabs(["✏️ 在线填写", "📁 上传文件"])

# ========== Tab1: 在线填写 ==========
with tab1:
    st.subheader("在线填写物资需求")

    # 构建初始数据
    default_data = {
        "场馆名称": venue_names,
        "通用赛事物资(kg)": [0] * len(venue_names),
        "专项运动器材(kg)": [0] * len(venue_names),
        "医疗物资(kg)": [0] * len(venue_names),
        "IT设备(kg)": [0] * len(venue_names),
    }

    # 如果已有物资数据，用已有数据填充
    if st.session_state.get("demands_df") is not None:
        df = st.session_state["demands_df"].copy()
        # 确保列一致，补充缺失的场馆
        existing_venues = set(df["场馆名称"].tolist())
        for vn in venue_names:
            if vn not in existing_venues:
                new_row = {"场馆名称": vn}
                for col in WEIGHT_COLS:
                    new_row[col] = 0
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        # 只保留当前场馆
        df = df[df["场馆名称"].isin(venue_names)]
    else:
        df = pd.DataFrame(default_data)

    # 如果有 material_demands 历史数据，恢复它
    if "material_demands" in st.session_state and st.session_state.material_demands:
        for venue, categories in st.session_state.material_demands.items():
            if venue in venue_names:
                mask = df["场馆名称"] == venue
                for cat, materials in categories.items():
                    col_map = {
                        "通用赛事物资": "通用赛事物资(kg)",
                        "专项运动器材": "专项运动器材(kg)",
                        "医疗物资": "医疗物资(kg)",
                        "IT设备": "IT设备(kg)"
                    }
                    col_name = col_map.get(cat, None)
                    if col_name and col_name in df.columns:
                        total = sum(m.get("weight_kg", 0) for m in materials.values())
                        df.loc[mask, col_name] = total

    # 显示可编辑表格
    edited_df = st.data_editor(
        df,
        disabled=["场馆名称"],
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "通用赛事物资(kg)": st.column_config.NumberColumn(min_value=0, step=10, default=0),
            "专项运动器材(kg)": st.column_config.NumberColumn(min_value=0, step=10, default=0),
            "医疗物资(kg)": st.column_config.NumberColumn(min_value=0, step=10, default=0),
            "IT设备(kg)": st.column_config.NumberColumn(min_value=0, step=10, default=0),
        }
    )

    # 计算每行总计
    edited_df["总需求(kg)"] = edited_df[WEIGHT_COLS].sum(axis=1)

    # 显示每列合计
    st.markdown("---")
    st.subheader("📊 各列合计")
    col_sum1, col_sum2, col_sum3, col_sum4, col_sum5 = st.columns(5)
    with col_sum1:
        st.metric("通用赛事物资", f"{edited_df['通用赛事物资(kg)'].sum():,.0f} kg")
    with col_sum2:
        st.metric("专项运动器材", f"{edited_df['专项运动器材(kg)'].sum():,.0f} kg")
    with col_sum3:
        st.metric("医疗物资", f"{edited_df['医疗物资(kg)'].sum():,.0f} kg")
    with col_sum4:
        st.metric("IT设备", f"{edited_df['IT设备(kg)'].sum():,.0f} kg")
    with col_sum5:
        st.metric("总计", f"{edited_df['总需求(kg)'].sum():,.0f} kg")

    st.markdown("---")

    # 保存按钮
    if st.button("💾 保存物资需求", type="primary", use_container_width=True):
        # 保存完整的 DataFrame
        st.session_state["demands_df"] = edited_df.copy()

        # 同时保存为 dict 格式，方便路径优化页面读取
        # 保存结构：{场馆名: {物资类别: 数量, ...}}
        demands = {}
        for _, row in edited_df.iterrows():
            venue = row["场馆名称"]
            general = float(row.get("通用赛事物资(kg)", 0) or 0)
            sports = float(row.get("专项运动器材(kg)", 0) or 0)
            medical = float(row.get("医疗物资(kg)", 0) or 0)
            it_equip = float(row.get("IT设备(kg)", 0) or 0)
            demands[venue] = {
                "通用赛事物资": general,
                "专项运动器材": sports,
                "医疗物资": medical,
                "IT设备": it_equip,
                "总需求": general + sports + medical + it_equip
            }

        st.session_state["demands"] = demands

        # 同步到 material_demands（供其他页面使用）
        st.session_state.material_demands = {}
        for _, row in edited_df.iterrows():
            venue = row["场馆名称"]
            for col in WEIGHT_COLS:
                cat_name = col.replace("(kg)", "")
                weight = row[col]
                if weight > 0:
                    if venue not in st.session_state.material_demands:
                        st.session_state.material_demands[venue] = {}
                    if cat_name not in st.session_state.material_demands[venue]:
                        st.session_state.material_demands[venue][cat_name] = {}
                    st.session_state.material_demands[venue][cat_name]["总计"] = {
                        "weight_kg": weight,
                        "volume_m3": 0,
                        "urgency": "中"
                    }

        st.success(f"✅ 已保存 {len(demands)} 个场馆的物资需求，总物资量 {edited_df['总需求(kg)'].sum():,.0f} kg")

    # 预览编辑后的表格
    with st.expander("📋 预览完整数据"):
        st.dataframe(edited_df, hide_index=True, use_container_width=True)


# ========== Tab2: 上传文件 ==========
with tab2:
    st.subheader("上传文件导入物资需求")

    st.info("""
    **支持格式：** CSV、Excel(.xlsx/.xls)、TXT、JSON
    **编码：** 自动识别（UTF-8/GBK/GB2312）
    """)
    st.caption("必需列：场馆名称 + 各物资类别重量（通用赛事物资、专项运动器材、医疗物资、IT设备）")

    uploaded_file = st.file_uploader(
        "上传物资需求文件",
        type=["csv", "xlsx", "xls", "txt", "json"],
        help="支持 CSV、Excel、TXT、JSON 格式"
    )

    if uploaded_file:
        df_upload, error = read_uploaded_file(uploaded_file)
        if error:
            st.error(f"❌ {error}")
        elif df_upload is not None and len(df_upload) > 0:
            st.success(f"✅ 成功读取 {len(df_upload)} 条数据")
            st.dataframe(df_upload, use_container_width=True)
            st.info(f"共读取 {len(df_upload)} 条记录")

            # 智能匹配列名
            columns = df_upload.columns.tolist()
            venue_col = None
            weight_cols_map = {
                "通用赛事物资(kg)": None,
                "专项运动器材(kg)": None,
                "医疗物资(kg)": None,
                "IT设备(kg)": None
            }

            for col in columns:
                col_lower = str(col).lower()
                col_str = str(col).strip()
                if '场馆' in col_str or '名称' in col_str or 'venue' in col_lower or 'name' in col_lower:
                    venue_col = col
                for cat_key in weight_cols_map.keys():
                    cat_lower = cat_key.lower().replace("(kg)", "").strip()
                    if cat_lower in col_lower or cat_key.replace("(kg)", "") in col_str:
                        weight_cols_map[cat_key] = col

            # 如果找不到场馆列，列出供选择
            if venue_col is None:
                st.warning("未能自动识别【场馆名称】列，请手动选择：")
                venue_col = st.selectbox("选择【场馆名称】列", columns)

            # 显示列映射状态
            st.markdown("---")
            st.markdown("**列映射状态：**")
            cols_status = st.columns(5)
            with cols_status[0]:
                st.write(f"场馆名称: `{venue_col if venue_col else '❌ 未找到'}`")
            for i, (cat, matched_col) in enumerate(weight_cols_map.items()):
                with cols_status[i + 1]:
                    status = "✅" if matched_col else "❌"
                    st.write(f"{status} {cat}")

            # 让用户确认或修正列映射
            with st.expander("🔧 手动调整列映射"):
                venue_col = st.selectbox("场馆名称列", columns, index=columns.index(venue_col) if venue_col in columns else 0)
                for cat in weight_cols_map.keys():
                    current = weight_cols_map[cat]
                    options = [None] + [c for c in columns if c != venue_col]
                    idx = options.index(current) if current in options else 0
                    weight_cols_map[cat] = st.selectbox(f"{cat}列", options, index=idx)

            if st.button("🚀 确认并合并到数据表", type="primary"):
                # 构建上传数据的 DataFrame
                upload_data = {"场馆名称": df_upload[venue_col].astype(str)}

                for cat, col in weight_cols_map.items():
                    if col:
                        upload_data[cat] = pd.to_numeric(df_upload[col], errors="coerce").fillna(0)
                    else:
                        upload_data[cat] = 0

                df_upload_mapped = pd.DataFrame(upload_data)

                # 合并到主数据表
                if st.session_state.get("demands_df") is not None:
                    df_main = st.session_state["demands_df"].copy()
                    # 用上传数据更新已有数据
                    for _, row in df_upload_mapped.iterrows():
                        venue = row["场馆名称"]
                        mask = df_main["场馆名称"] == venue
                        if mask.any():
                            for cat in WEIGHT_COLS:
                                df_main.loc[mask, cat] = row[cat]
                        else:
                            df_main = pd.concat([df_main, row.to_frame().T], ignore_index=True)
                    st.session_state["demands_df"] = df_main
                else:
                    # 补充缺失列
                    for col in WEIGHT_COLS:
                        if col not in df_upload_mapped.columns:
                            df_upload_mapped[col] = 0
                    st.session_state["demands_df"] = df_upload_mapped

                # 同步 demands（使用分类结构）
                demands = {}
                df_save = st.session_state["demands_df"]
                for _, row in df_save.iterrows():
                    venue = row["场馆名称"]
                    general = float(row.get("通用赛事物资(kg)", 0) or 0)
                    sports = float(row.get("专项运动器材(kg)", 0) or 0)
                    medical = float(row.get("医疗物资(kg)", 0) or 0)
                    it_equip = float(row.get("IT设备(kg)", 0) or 0)
                    demands[venue] = {
                        "通用赛事物资": general,
                        "专项运动器材": sports,
                        "医疗物资": medical,
                        "IT设备": it_equip,
                        "总需求": general + sports + medical + it_equip
                    }
                st.session_state["demands"] = demands

                st.success(f"✅ 已合并 {len(df_upload_mapped)} 条记录到物资需求表！")
                st.rerun()

    # 模板下载
    st.markdown("---")
    st.subheader("📥 下载导入模板")
    template_data = {
        "场馆名称": ["主体育场", "游泳中心", "运动员村"],
        "通用赛事物资(kg)": [500, 1000, 300],
        "专项运动器材(kg)": [300, 500, 200],
        "医疗物资(kg)": [100, 200, 150],
        "IT设备(kg)": [200, 300, 100],
    }
    df_template = pd.DataFrame(template_data)
    csv_template = df_template.to_csv(index=False)
    st.download_button(
        label="下载CSV模板",
        data=csv_template,
        file_name="material_demand_template.csv",
        mime="text/csv"
    )


# ========== 底部需求摘要 ==========
st.markdown("---")
st.divider()
st.subheader("📋 当前已保存的物资需求数据")

if st.session_state.get("demands") and len(st.session_state["demands"]) > 0:
    demands = st.session_state["demands"]
    total_demand = sum(v.get("总需求", 0) for v in demands.values())

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("场馆数", len(demands))
    with col_m2:
        st.metric("总物资需求量", f"{total_demand:,.0f} kg")
    with col_m3:
        avg_demand = total_demand / len(demands) if demands else 0
        st.metric("场均需求", f"{avg_demand:,.0f} kg")

    # 显示汇总表
    summary_list = [{"场馆": k, "总需求(kg)": v.get("总需求", 0)} for k, v in demands.items()]
    st.dataframe(pd.DataFrame(summary_list), hide_index=True, use_container_width=True)

    st.success("✅ 数据已同步，可供【路径优化】页面使用")
else:
    st.warning("⚠️ 暂无物资需求数据，请通过上方在线填写或上传文件录入。")

st.markdown("---")
st.caption("💡 提示: 物资需求数据将用于VRP路径优化中的车辆调度计算")
