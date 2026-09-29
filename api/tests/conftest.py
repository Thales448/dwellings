import os
import tempfile
from pathlib import Path

_data = Path(tempfile.mkdtemp(prefix="dwl-test-"))
os.environ["DATA_DIR"] = str(_data)
os.environ["DATABASE_URL"] = f"sqlite:///{_data / 'dwellings.db'}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["TOKEN_PEPPER"] = "test-pepper"
os.environ["PUBLIC_URL"] = "https://dwellings.rtech.cloud"
os.environ["WEBAUTHN_RP_ID"] = "dwellings.rtech.cloud"
os.environ["STATIC_DIR"] = str(_data / "missing-static")
