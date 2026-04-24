"""Local Streamlit pages package.

This file makes the `pages` directory an explicit Python package so imports like
`from pages._ui_shared import ...` resolve to the local project code reliably in
different deployment environments, including Streamlit Cloud.
"""
