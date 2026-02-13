import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

try:
    from fyers_apiv3 import fyersModel
except ImportError as e:
    raise SystemExit("Missing dependency. Run: pip install -r requirements.txt") from e


TOKEN_PATH = Path(__file__).resolve().parents[1] / "data" / "fyers_token.json"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python fyers_auth_exchange_token.py <AUTH_CODE>")

    auth_code = sys.argv[1].strip()

    load_dotenv()
    app_id = os.environ.get("FYERS_APP_ID")
    secret_key = os.environ.get("FYERS_SECRET_KEY")
    redirect_uri = os.environ.get("FYERS_REDIRECT_URI")

    if not app_id or not secret_key or not redirect_uri:
        raise SystemExit("Set FYERS_APP_ID, FYERS_SECRET_KEY, FYERS_REDIRECT_URI in .env")

    session = fyersModel.SessionModel(
        client_id=app_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
    )

    session.set_token(auth_code)
    resp = session.generate_token()

    if not isinstance(resp, dict) or resp.get("access_token") is None:
        print("Token exchange failed. Response:")
        print(resp)
        raise SystemExit(2)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(resp, indent=2))

    print(f"Saved token to: {TOKEN_PATH}")


if __name__ == "__main__":
    main()
