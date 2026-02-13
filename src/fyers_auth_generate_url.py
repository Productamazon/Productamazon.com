import os
from dotenv import load_dotenv

# FYERS v3 auth flow: generate login URL → user logs in → receives auth_code → exchange for access_token.

try:
    from fyers_apiv3 import fyersModel
except ImportError as e:
    raise SystemExit("Missing dependency. Run: pip install -r requirements.txt") from e


def main():
    load_dotenv()
    app_id = os.environ.get("FYERS_APP_ID")
    redirect_uri = os.environ.get("FYERS_REDIRECT_URI")

    if not app_id or not redirect_uri:
        raise SystemExit("Set FYERS_APP_ID and FYERS_REDIRECT_URI in .env")

    session = fyersModel.SessionModel(
        client_id=app_id,
        redirect_uri=redirect_uri,
        response_type="code",
        state="paper_trading_bot",
        grant_type="authorization_code",
    )

    url = session.generate_authcode()
    print(url)


if __name__ == "__main__":
    main()
