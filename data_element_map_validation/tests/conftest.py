"""
Mock streamlit before curator_review_app is imported so tests run without a
running Streamlit server. Must be imported (via conftest.py auto-loading) before
any test module imports the app.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Make @st.cache_data a no-op pass-through decorator that adds a .clear() stub.
def _passthrough_cache(func=None, **kwargs):
    if func is not None:
        func.clear = MagicMock()
        return func
    def decorator(f):
        f.clear = MagicMock()
        return f
    return decorator

st_mock = MagicMock()
st_mock.cache_data = _passthrough_cache
sys.modules["streamlit"] = st_mock

# Put the app directory on the path so tests can import curator_review_app.
sys.path.insert(0, str(Path(__file__).parent.parent))
