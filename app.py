from __future__ import annotations

import streamlit as st

from config import APP_NAME, APP_TAGLINE, ASSETS_DIR
from frontend import dashboard_page


def _load_css() -> None:
    css_path = ASSETS_DIR / "styles.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="assets/ocha_mark.svg",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _load_css()
    dashboard_page.render()


if __name__ == "__main__":
    main()
