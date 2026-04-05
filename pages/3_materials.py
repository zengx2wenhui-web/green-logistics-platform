"""物资需求页面"""
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="物资需求", page_icon="📦")


def read_csv_with_encoding(uploaded_file):
    """尝试多种编码读取CSV文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']
    for encoding in encodings:
        try:
            return pd.read_csv(uploaded_file, encoding=encoding)
        except UnicodeDecodeError:
            continue
    # 如果都失败，尝试二进制读取后解码
    uploaded_file.seek(0)
    content = uploaded_file.read()
    return pd.read_csv(content, encoding='utf-8', errors='replace')

st.title("📦 Step 3：物资需求")
st.markdown("为各场馆录入物资配送需求")

# 物资类型定义
MATERIAL_CATEGORIES = {
    "器材设备": ["比赛器材", "训练器材", "音响设备", "照明设备", "空调设备"],
    "生活物资": ["餐饮原料", "清洁用品", "床上用品", "日常生活用品"],
    "医疗保障": ["医疗设备", "药品耗材", "急救物资", "防护用品"],
    "媒体物资": ["转播设备", "摄影器材", "办公用品", "通信设备"],
    "安保物资": ["安保设备", "监控设备", "消防器材", "警戒用品"],
    "其他物资": ["包装材料", "办公设备", "后勤物资", "其他"]
}

# 初始化session_state
if "material_demands" not in st.session_state:
    st.session_state.material_demands = {}

if "demands" not in st.session_state:
    st.session_state.demands = {}


def sync_demands_from_material_demands():
    """从material_demands计算每个场馆的总需求并同步到demands"""
    st.session_state.demands = {}
    for venue, categories in st.session_state.material_demands.items():
        total_weight = 0
        for materials in categories.values():
            for mat_info in materials.values():
                total_weight += mat_info.get("weight_kg", 0)
        st.session_state.demands[venue] = total_weight


# 获取已录入的场馆列表
def get_venue_names():
    if "venues" in st.session_state and st.session_state.venues:
        return [v["name"] for v in st.session_state.venues]
    return []

venue_names = get_venue_names()

if not venue_names:
    st.warning("⚠️ 请先在「场馆录入」页面添加场馆后再录入物资需求")

    # 显示导入提示
    st.info("""
    **物资需求CSV格式：**
    - 必需列：`场馆名称`、`物资类别`、`物资名称`、`重量_kg`
    - 可选列：`体积_m3`、`紧急程度`、`备注`
    """)
    st.stop()

tab1, tab2, tab3 = st.tabs(["📁 CSV批量导入", "✏️ 在线表单录入", "📋 需求汇总"])

with tab1:
    st.subheader("CSV文件批量导入物资需求")

    st.info("""
    **CSV文件格式要求：**
    - `场馆名称` - 必填，需与已录入场馆名称一致
    - `物资类别` - 必填，如：器材设备、生活物资
    - `物资名称` - 必填，具体物资名称
    - `重量_kg` - 必填，重量（千克）
    - `体积_m3` - 可选，体积（立方米）
    - `紧急程度` - 可选：高/中/低
    """)

    uploaded_file = st.file_uploader("选择CSV文件", type=["csv"])

    if uploaded_file:
        try:
            df = read_csv_with_encoding(uploaded_file)
            st.write("文件预览：")
            st.dataframe(df.head(10), hide_index=True)

            required_cols = ["场馆名称", "物资类别", "物资名称", "重量_kg"]
            missing_cols = [col for col in required_cols if col not in df.columns]

            if missing_cols:
                st.error(f"缺少必需列: {', '.join(missing_cols)}")
            else:
                if st.button("🚀 导入物资需求", type="primary"):
                    imported_count = 0
                    for _, row in df.iterrows():
                        venue = row["场馆名称"]
                        category = row["物资类别"]
                        material = row["物资名称"]
                        weight = float(row.get("重量_kg", 0))
                        volume = float(row.get("体积_m3", 0)) if pd.notna(row.get("体积_m3")) else 0.0
                        urgency = str(row.get("紧急程度", "中"))

                        if venue not in st.session_state.material_demands:
                            st.session_state.material_demands[venue] = {}

                        if category not in st.session_state.material_demands[venue]:
                            st.session_state.material_demands[venue][category] = {}

                        st.session_state.material_demands[venue][category][material] = {
                            "weight_kg": weight,
                            "volume_m3": volume,
                            "urgency": urgency
                        }
                        imported_count += 1

                    # 同步更新 demands
                    sync_demands_from_material_demands()
                    st.success(f"成功导入 {imported_count} 条物资需求记录！")

        except Exception as e:
            st.error(f"文件读取失败: {e}")

    # 模板下载
    st.markdown("---")
    st.subheader("📥 下载导入模板")

    template_data = {
        "场馆名称": ["主体育场", "游泳中心", "运动员村"],
        "物资类别": ["器材设备", "生活物资", "器材设备"],
        "物资名称": ["比赛器材A", "餐饮原料", "训练器材"],
        "重量_kg": [500, 1000, 300],
        "体积_m3": [2.0, 5.0, 1.5],
        "紧急程度": ["高", "中", "低"]
    }
    df_template = pd.DataFrame(template_data)

    csv_template = df_template.to_csv(index=False)
    st.download_button(
        label="下载CSV模板",
        data=csv_template,
        file_name="material_demand_template.csv",
        mime="text/csv"
    )

with tab2:
    st.subheader("在线表单逐条录入")

    # 选择场馆
    selected_venue = st.selectbox("选择场馆 *", [""] + venue_names)

    if selected_venue:
        # 初始化该场馆的需求
        if selected_venue not in st.session_state.material_demands:
            st.session_state.material_demands[selected_venue] = {}

        # 选择物资类别
        selected_category = st.selectbox(
            "物资类别 *",
            [""] + list(MATERIAL_CATEGORIES.keys())
        )

        if selected_category:
            # 选择或输入物资名称
            category_materials = MATERIAL_CATEGORIES[selected_category]

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                material_input_mode = st.radio(
                    "物资名称输入方式",
                    ["从列表选择", "手动输入"],
                    horizontal=True
                )

            if material_input_mode == "从列表选择":
                selected_material = st.selectbox("物资名称 *", [""] + category_materials)
            else:
                selected_material = st.text_input("物资名称 *", placeholder="输入物资名称")

            if selected_material:
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    weight = st.number_input(
                        "重量 (kg) *",
                        min_value=0.0,
                        value=0.0,
                        step=10.0,
                        format="%.1f"
                    )
                with col_w2:
                    volume = st.number_input(
                        "体积 (m³)",
                        min_value=0.0,
                        value=0.0,
                        step=0.5,
                        format="%.2f"
                    )

                urgency = st.selectbox(
                    "紧急程度",
                    ["高", "中", "低"],
                    index=1
                )

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    add_btn = st.button("➕ 添加物资", type="primary", use_container_width=True)
                with col_btn2:
                    clear_btn = st.button("🗑️ 清空此类", use_container_width=True)

                if add_btn and selected_material and weight > 0:
                    if selected_category not in st.session_state.material_demands[selected_venue]:
                        st.session_state.material_demands[selected_venue][selected_category] = {}

                    st.session_state.material_demands[selected_venue][selected_category][selected_material] = {
                        "weight_kg": weight,
                        "volume_m3": volume,
                        "urgency": urgency
                    }
                    # 同步更新 demands
                    sync_demands_from_material_demands()
                    st.success(f"已添加: {selected_material} ({weight} kg)")

                if clear_btn:
                    if selected_category in st.session_state.material_demands[selected_venue]:
                        del st.session_state.material_demands[selected_venue][selected_category]
                    # 同步更新 demands
                    sync_demands_from_material_demands()
                    st.rerun()

        # 显示当前场馆的物资列表
        st.markdown("---")
        st.subheader(f"📋 {selected_venue} 当前物资清单")

        venue_demands = st.session_state.material_demands.get(selected_venue, {})

        if venue_demands:
            # 构建显示数据
            display_data = []
            for cat, materials in venue_demands.items():
                for mat_name, mat_info in materials.items():
                    display_data.append({
                        "类别": cat,
                        "物资名称": mat_name,
                        "重量_kg": mat_info["weight_kg"],
                        "体积_m3": mat_info.get("volume_m3", 0),
                        "紧急度": mat_info.get("urgency", "中")
                    })

            if display_data:
                df_display = pd.DataFrame(display_data)
                st.dataframe(df_display, hide_index=True, width="stretch")

                # 统计
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    total_weight = df_display["重量_kg"].sum()
                    st.metric("总重量", f"{total_weight:,.1f} kg")
                with col_s2:
                    total_volume = df_display["体积_m3"].sum()
                    st.metric("总体积", f"{total_volume:,.2f} m³")
                with col_s3:
                    item_count = len(df_display)
                    st.metric("物资项数", item_count)

                # 删除物资
                st.markdown("**🗑️ 删除物资项**")
                material_options = [f"{row['类别']} - {row['物资名称']}" for _, row in df_display.iterrows()]
                selected_to_delete = st.selectbox("选择要删除的物资", [""] + material_options)

                if selected_to_delete and st.button("确认删除"):
                    cat_name, mat_name = selected_to_delete.split(" - ", 1)
                    if cat_name in st.session_state.material_demands[selected_venue]:
                        if mat_name in st.session_state.material_demands[selected_venue][cat_name]:
                            del st.session_state.material_demands[selected_venue][cat_name][mat_name]
                            if not st.session_state.material_demands[selected_venue][cat_name]:
                                del st.session_state.material_demands[selected_venue][cat_name]
                    # 同步更新 demands
                    sync_demands_from_material_demands()
                    st.rerun()
        else:
            st.info("该场馆暂无物资需求记录")

with tab3:
    st.subheader("物资需求汇总")

    if not venue_names:
        st.info("请先录入场馆和物资需求")
    else:
        # 构建汇总数据
        summary_data = []
        total_all_weight = 0
        total_all_volume = 0

        for venue in venue_names:
            venue_data = st.session_state.material_demands.get(venue, {})
            venue_weight = 0
            venue_volume = 0
            venue_items = 0

            for cat, materials in venue_data.items():
                for mat_name, mat_info in materials.items():
                    weight = mat_info["weight_kg"]
                    volume = mat_info.get("volume_m3", 0)
                    venue_weight += weight
                    venue_volume += volume
                    venue_items += 1

                    summary_data.append({
                        "场馆": venue,
                        "类别": cat,
                        "物资": mat_name,
                        "重量_kg": weight,
                        "体积_m3": volume,
                        "紧急度": mat_info.get("urgency", "中")
                    })

            total_all_weight += venue_weight
            total_all_volume += venue_volume

        if summary_data:
            df_summary = pd.DataFrame(summary_data)

            # 概览指标
            col_o1, col_o2, col_o3, col_o4 = st.columns(4)
            with col_o1:
                st.metric("场馆数", len(venue_names))
            with col_o2:
                st.metric("总物资项", len(df_summary))
            with col_o3:
                st.metric("总重量", f"{total_all_weight:,.1f} kg")
            with col_o4:
                st.metric("总体积", f"{total_all_volume:,.2f} m³")

            st.markdown("---")

            # 按场馆汇总
            st.subheader("按场馆汇总")
            venue_summary = df_summary.groupby("场馆").agg({
                "重量_kg": "sum",
                "体积_m3": "sum",
                "物资": "count"
            }).rename(columns={"物资": "物资项数"}).reset_index()

            st.dataframe(venue_summary, hide_index=True, width="stretch")

            # 可视化
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                fig_venue = px.bar(
                    venue_summary,
                    x="场馆",
                    y="重量_kg",
                    color="场馆",
                    title="各场馆物资重量分布",
                    text_auto=True
                )
                st.plotly_chart(fig_venue, width="stretch")

            with col_v2:
                category_summary = df_summary.groupby("类别")["重量_kg"].sum().reset_index()
                fig_cat = px.pie(
                    category_summary,
                    values="重量_kg",
                    names="类别",
                    title="物资类别重量占比"
                )
                st.plotly_chart(fig_cat, width="stretch")

            # 完整数据表
            with st.expander("查看完整数据"):
                st.dataframe(df_summary.sort_values(["场馆", "类别"]), hide_index=True, width="stretch")

            # 导出
            st.markdown("---")
            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                csv_export = df_summary.to_csv(index=False)
                st.download_button(
                    label="📥 导 出 CSV",
                    data=csv_export,
                    file_name="material_demands_summary.csv",
                    mime="text/csv"
                )
            with col_exp2:
                if st.button("🗑️ 清空所有物资数据"):
                    st.session_state.material_demands = {}
                    st.session_state.demands = {}
                    st.success("已清空所有物资需求数据")
                    st.rerun()
        else:
            st.info("暂无物资需求数据，请先录入")

st.markdown("---")
st.caption("💡 提示: 物资需求数据将用于VRP路径优化中的车辆调度计算")
