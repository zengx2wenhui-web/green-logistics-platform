from __future__ import annotations

import streamlit as st


def render_page_nav(
    prev_page: str | None,
    next_page: str | None,
    *,
    prev_label: str = "\u4e0a\u4e00\u6b65",
    next_label: str = "\u4e0b\u4e00\u6b65",
    key_prefix: str = "glp-nav",
    can_go_next: bool = True,
    next_block_message: str | None = None,
) -> None:
    st.markdown(
        """
        <style>
        .glp-bottom-nav-wrap {
            margin-top: 1.85rem;
        }

        [class*="st-key-"][class*="-nav-prev"] button,
        [class*="st-key-"][class*="-nav-next"] button {
            background: transparent !important;
            color: #111111 !important;
            border: 0 !important;
            border-bottom: 1px solid #333333 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            font-size: 1.5rem !important;
            font-weight: 400 !important;
            height: auto !important;
            min-height: 0 !important;
            padding: 0 1.2rem 0.2rem !important;
        }

        [class*="st-key-"][class*="-nav-prev"] button:hover,
        [class*="st-key-"][class*="-nav-prev"] button:focus,
        [class*="st-key-"][class*="-nav-prev"] button:active,
        [class*="st-key-"][class*="-nav-next"] button:hover,
        [class*="st-key-"][class*="-nav-next"] button:focus,
        [class*="st-key-"][class*="-nav-next"] button:active {
            background: transparent !important;
            color: #111111 !important;
            border: 0 !important;
            border-bottom: 1px solid #333333 !important;
            box-shadow: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="glp-bottom-nav-wrap">', unsafe_allow_html=True)
    next_blocked = False
    if prev_page and next_page:
        _, prev_col, _, next_col, _ = st.columns([2.4, 1, 0.45, 1, 2.4])
        with prev_col:
            if st.button(prev_label, key=f"{key_prefix}-prev", width='stretch'):
                st.switch_page(prev_page)
        with next_col:
            if st.button(next_label, key=f"{key_prefix}-next", width='stretch'):
                if can_go_next:
                    st.switch_page(next_page)
                else:
                    next_blocked = True
    elif prev_page:
        _, prev_col, _ = st.columns([2.8, 1, 2.8])
        with prev_col:
            if st.button(prev_label, key=f"{key_prefix}-prev", width='stretch'):
                st.switch_page(prev_page)
    elif next_page:
        _, next_col, _ = st.columns([2.8, 1, 2.8])
        with next_col:
            if st.button(next_label, key=f"{key_prefix}-next", width='stretch'):
                if can_go_next:
                    st.switch_page(next_page)
                else:
                    next_blocked = True
    if next_blocked and next_block_message:
        st.warning(next_block_message)
    st.markdown("</div>", unsafe_allow_html=True)
