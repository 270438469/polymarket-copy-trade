from dotenv import load_dotenv
import os

from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON


def main():
    host = "https://clob.polymarket.com"
    key = os.getenv("PK")
    chain_id = POLYGON
    funder = os.getenv("FUNDER")
    client = ClobClient(host, key=key, chain_id=chain_id, signature_type=2, funder=funder)

    try:
        api_creds = client.create_or_derive_api_creds()
        print("API Key:", api_creds.api_key)
        print("Secret:", api_creds.api_secret)
        print("Passphrase:", api_creds.api_passphrase)
    except Exception as e:
        print("Error creating API:", e)

if __name__ == "__main__":
    # Set proxy first
    os.environ['HTTP_PROXY'] = 'http://localhost:15236'
    os.environ['HTTPS_PROXY'] = 'http://localhost:15236'
    main()