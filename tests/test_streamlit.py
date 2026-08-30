"""Smoke test for the Streamlit app."""


def test_streamlit_app_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("ui/streamlit_app.py", default_timeout=20).run()
    assert not at.exception
