import json
import logging
import os
import pandas as pd
import requests
from typing import Dict, List, Generator
from pprint import pprint
from datetime import datetime, timedelta
from dotenv import load_dotenv
from web3 import Web3
from function.func_backtest import WalletBacktest
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SmartWalletFinder:
    def __init__(self):
        """Initialize SmartWalletFinder with necessary configurations"""
        load_dotenv()
        
        # Initialize WalletBacktest
        api_key = os.getenv('POLYGONSCAN_API_KEY')
        if not api_key:
            raise ValueError("POLYGONSCAN_API_KEY not set in environment")
            
        self.backtest = WalletBacktest(api_key, None)  # We don't need ClobClient for searching
        self.w3 = self.backtest.w3  # Use Web3 instance from WalletBacktest
        self.contract_abis = self.backtest.contract_abis  # Use contract ABIs from WalletBacktest
        
        # Initialize data structures
        self.active_wallets: Dict[str, Dict] = {}  # wallet -> trade data

    def get_transactions_in_window(self, contract_address: str, start_block: int, end_block: int) -> List[Dict]:
        """Get transactions for a contract within a specific block range"""
        base_url = "https://api.polygonscan.com/api"
        
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': contract_address,
            'startblock': start_block,
            'endblock': end_block,
            'page': 1,
            'offset': 10000,  # Maximum records per request
            'sort': 'desc',
            'apikey': self.backtest.api_key
        }
        
        proxies = {
            'http': os.getenv('HTTP_PROXY'),
            'https': os.getenv('HTTPS_PROXY')
        }
        
        try:
            response = requests.get(base_url, params=params, proxies=proxies)
            data = response.json()
            
            if data['status'] == '1':
                transactions = data['result']
                # if transactions:
                #     logger.info(f"Block range: {transactions[-1]['blockNumber']} to {transactions[0]['blockNumber']}")
                #     logger.info(f"Time range: {datetime.fromtimestamp(int(transactions[-1]['timeStamp']))} to {datetime.fromtimestamp(int(transactions[0]['timeStamp']))}")
                return transactions
            else:
                logger.error(f"Error getting transactions: {data['message']}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to get transactions: {e}")
            return []

    def get_block_by_timestamp(self, timestamp: int) -> int:
        """Get the closest block number for a given timestamp"""
        base_url = "https://api.polygonscan.com/api"
        
        params = {
            'module': 'block',
            'action': 'getblocknobytime',
            'timestamp': timestamp,
            'closest': 'before',
            'apikey': self.backtest.api_key
        }
        
        proxies = {
            'http': os.getenv('HTTP_PROXY'),
            'https': os.getenv('HTTPS_PROXY')
        }
        
        try:
            response = requests.get(base_url, params=params, proxies=proxies)
            data = response.json()
            
            if data['status'] == '1':
                return int(data['result'])
            else:
                logger.error(f"Error getting block number: {data['message']}")
                return 0
                
        except Exception as e:
            logger.error(f"Failed to get block number: {e}")
            return 0

    def get_transaction_batches(self, contract_address: str, hours: int) -> Generator[List[Dict], None, None]:
        """Generate batches of transactions using block ranges"""
        # Get current block
        current_block = self.w3.eth.block_number
        # logger.info(f"Current block: {current_block}")
        
        # Get block number from hours ago
        timestamp = int(datetime.now().timestamp()) - (hours * 3600)
        start_block = self.get_block_by_timestamp(timestamp)
        # logger.info(f"Start block: {start_block} (from {datetime.fromtimestamp(timestamp)})")
        
        if start_block == 0:
            logger.error("Failed to get start block")
            return
        
        # Calculate block range for each batch (approximately 1 hour worth of blocks)
        blocks_per_batch = 1800  # 3600/2 = 1800 blocks per hour(2 seconds per block)
        
        current_start = start_block
        while current_start < current_block:
            current_end = min(current_start + blocks_per_batch, current_block)
            
            transactions = self.get_transactions_in_window(
                contract_address, 
                current_start,
                current_end
            )
            
            if transactions:
                yield transactions
                
            # Add a small delay to avoid API rate limits
            time.sleep(0.5)
            
            # Move to next block range
            current_start = current_end + 1

    def update_wallet_stats(self, wallet: str, trade_data: Dict):
        """Update trading statistics for a wallet"""
        if wallet not in self.active_wallets:
            self.active_wallets[wallet] = {
                'trade_count': 0,
                'tokens_traded': set(),
                'trades': []
            }
            
        stats = self.active_wallets[wallet]
        stats['trade_count'] += 1
        stats['tokens_traded'].add(trade_data['tokenId'])
        stats['trades'].append({
            'timestamp': trade_data['timestamp'],
            'tokenId': trade_data['tokenId'],
            'amount': float(trade_data['makerAmount']),
            'side': 'BUY' if trade_data['side'] == 0 else 'SELL',
            'hash': trade_data['hash']
        })

    def analyze_wallets(self) -> pd.DataFrame:
        """Analyze collected wallet data and return potential smart wallets"""
        wallet_data = []
        
        for wallet, stats in self.active_wallets.items():
            wallet_data.append({
                'wallet': wallet,
                'trade_count': stats['trade_count'],
                'unique_tokens': len(stats['tokens_traded']),
            })
        df = pd.DataFrame(wallet_data)

        # screen df
        df = df[df['trade_count'] >= 5]
        
        if not df.empty:
            # Define scoring weights
            score_weights = {
                'unique_tokens': 0.2,
                'trade_count': 0.8
            }
            
            # Standardize metrics (z-score normalization)
            metrics_to_standardize = ['trade_count', 'unique_tokens']
            standardized_df = df.copy()
            
            for metric in metrics_to_standardize:
                mean = df[metric].mean()
                std = df[metric].std()
                if std != 0:  # Avoid division by zero
                    standardized_df[f'{metric}_std'] = (df[metric] - mean) / std
                else:
                    standardized_df[f'{metric}_std'] = 0  # If std is 0, all values are the same
            
            # Calculate smart score using standardized metrics
            df['active_score'] = (
                standardized_df['trade_count_std'] * score_weights['trade_count'] +
                standardized_df['unique_tokens_std'] * score_weights['unique_tokens']
            )
            
            # Sort by smart score
            df = df.sort_values('active_score', ascending=False)
        
        return df

    def save_results(self, df: pd.DataFrame, hours: int):
        """Save analysis results to CSV"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        output_dir = 'assets/outcome'
        os.makedirs(output_dir, exist_ok=True)
        
        # Save detailed results
        output_file = f"{output_dir}/active_wallets_{timestamp}_{hours}h.csv"
        df.to_csv(output_file, index=False)
        logger.info(f"Saved to {output_file}")

    def decode_transaction_input(self, input_data: str) -> Dict:
        """Decode transaction input data"""
        decoded_data = []
        if input_data.startswith('0x'):
            input_data = input_data[2:]
        
        # Get contract instance
        contract = self.w3.eth.contract(abi=self.contract_abis['FEE_MODULE'])
        
        # Get function signature (first 4 bytes / 8 characters of input)
        func_signature = '0x' + input_data[:8]
        
        # Check if this is the specific function signature we're looking for
        if func_signature.startswith(self.backtest.match_orders_signature):  # matchOrders methodID 0xd2539b37
            try:
                # Decode input data
                decoded = contract.decode_function_input('0x' + input_data)
                decoded_data.append({
                    'maker': decoded[1]['takerOrder'].get('maker', ''),
                    'signer': decoded[1]['takerOrder'].get('signer', ''),
                    'tokenId': decoded[1]['takerOrder'].get('tokenId', ''),
                    'makerAmount': decoded[1]['takerOrder'].get('makerAmount', ''),
                    'side': decoded[1]['takerOrder'].get('side', ''),
                    'signatureType': decoded[1]['takerOrder'].get('signatureType', ''),
                    'function_name': 'matchOrders'
                })
            except Exception as e:
                logger.debug(f"Failed to decode input for tx: {e}")
                decoded_data.append({})
        else:
            logger.debug(f"Skipping non-target function signature: {func_signature}")
            decoded_data.append({})
        return decoded_data[0] if decoded_data else {}

    def find_smart_wallets(self, hours: int):
        """Find smart wallets from historical transactions"""
        logger.info(f"Searching for smart wallets in the last {hours} hours...")
        
        total_tx_count = 0
        
        # Get transactions for each Polymarket contract
        
        for name, address in {k: v for k, v in self.backtest.POLYMARKET_CONTRACTS.items() if k in ['FEE_MODULE', 'NEG_RISK_FEE_MODULE']}.items():
            logger.info(f"Getting transactions for {name}...")
            
            # Process transactions in batches by time window
            for batch in self.get_transaction_batches(address, hours):
                batch_size = len(batch)
                total_tx_count += batch_size
                logger.info(f"Processing batch of {batch_size} transactions...")
                
                # Process each transaction in the batch
                for tx in batch:
                    if tx.get('input', '').startswith(self.backtest.match_orders_signature):
                        decoded = self.decode_transaction_input(tx.get('input', ''))
                        if decoded and 'maker' in decoded:
                            trade_data = {
                                'maker': decoded['maker'],
                                'makerAmount': decoded['makerAmount'],
                                'tokenId': decoded['tokenId'],
                                'side': decoded['side'],
                                'timestamp': datetime.fromtimestamp(int(tx['timeStamp'])),
                                'hash': tx['hash']
                            }
                            if trade_data['maker']:
                                self.update_wallet_stats(trade_data['maker'], trade_data)

        # Analyze and save results
        logger.info(f"Processed TOTAL {total_tx_count} transactions")
        logger.info(f"Found {len(self.active_wallets)} active wallets")
        results_df = self.analyze_wallets()
        self.save_results(results_df, hours)
        logger.info("---- DONE ----")
        
        return results_df

def main():
    # Set proxy from environment variables
    load_dotenv()
    os.environ['HTTP_PROXY'] = os.getenv('HTTP_PROXY')
    os.environ['HTTPS_PROXY'] = os.getenv('HTTPS_PROXY')
    
    finder = SmartWalletFinder()
    finder.find_smart_wallets(hours=5)

if __name__ == "__main__":
    now = datetime.now()
    main()
    logger.info(f"Total time: {datetime.now() - now}")
