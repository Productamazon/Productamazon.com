import json
import os
from pathlib import Path
from dotenv import load_dotenv

try:
    from fyers_apiv3 import fyersModel
except ImportError as e:
    raise SystemExit("Missing dependency. Run: pip install -r requirements.txt") from e

TOKEN_PATH = Path(__file__).resolve().parents[1] / "data" / "fyers_token.json"


def load_access_token() -> str:
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(
            f"{TOKEN_PATH} not found. Run auth flow to create token."
        )
    data = json.loads(TOKEN_PATH.read_text())
    token = data.get("access_token")
    if not token:
        raise ValueError("access_token missing in token file")
    return token


def get_fyers():
    load_dotenv()
    app_id = os.environ.get("FYERS_APP_ID")
    if not app_id:
        raise SystemExit("Set FYERS_APP_ID in .env")

    access_token = load_access_token()
    return fyersModel.FyersModel(
        client_id=app_id,
        token=access_token,
        log_path=None,
    )
