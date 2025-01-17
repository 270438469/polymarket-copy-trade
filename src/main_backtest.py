import os
import logging
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
from pprint import pprint

from _py_clob_client.client import ClobClient
from _py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON
from function.func_backtest import WalletBacktest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_polymarket_transactions(address: str, output_file: str):
    """
    Get all USDC token transfers for an address and save to CSV
    
    Args:
        address: The address to get transactions for
        output_file: Output CSV file name
    """
    # Get Polygonscan API key from environment
    api_key = os.getenv("POLYGONSCAN_API_KEY")
    if not api_key:
        raise ValueError("POLYGONSCAN_API_KEY not set in environment")
    
    # Initialize ClobClient
    creds = ApiCreds(
        api_key=os.getenv("CLOB_API_KEY"),
        api_secret=os.getenv("CLOB_SECRET"),
        api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
    )
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=os.getenv('PK'), 
        chain_id=POLYGON,
        creds=creds
    )
    
    # Initialize WalletBacktest
    backtest = WalletBacktest(api_key, client)
    
    # Download all transactions
    # print(f"Downloading target transactions for {address}...")
    transactions = backtest.download_transactions(address)
    
    if not transactions:
        print("No target transactions found")
        return
    
    # Process transactions and save to CSV
    df = backtest.process_transactions(transactions, address)
    backtest.save_to_csv(df, output_file)


if __name__ == "__main__":
    load_dotenv()
    os.environ['HTTP_PROXY'] = os.getenv('HTTP_PROXY')
    os.environ['HTTPS_PROXY'] = os.getenv('HTTPS_PROXY')
    counter = 0

    now = datetime.now()

    active_wallets_file = "assets/outcome/active_wallets_20250114_1918_1h.csv"
    wallets = ['0x1638095947833f43a732e0da2ca9c3548887339b']
    wallets_df = pd.read_csv(active_wallets_file)
    
    # Process each wallet address
    # for wallet in wallets_df['wallet']:
    for wallet in wallets:
        counter += 1
        print(f"\nProcessing wallet: {wallet} || ({counter}/{len(wallets_df)})")
        # output_file = f"assets/outcome/backtest/{wallet}.csv"
        output_file = f"assets/outcome/{wallet}.csv"
        try:
            get_polymarket_transactions(wallet, output_file)
        except Exception as e:
            print(f"Error processing wallet {wallet}: {e}")
            continue

    logger.info(f"Total time: {datetime.now() - now}")

