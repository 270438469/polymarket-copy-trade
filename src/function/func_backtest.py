import os
import json
import requests
import pandas as pd
from pprint import pprint
from web3 import Web3
from web3.middleware import geth_poa_middleware
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from _py_clob_client.client import ClobClient
from utils.utils import get_position_all


class WalletBacktest:
    # Polymarket contract addresses
    POLYMARKET_CONTRACTS = {
        "CTF_EXCHANGE": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E".lower(),
        "NEG_RISK_CTF_EXCHANGE": "0xC5d563A36AE78145C45a50134d48A1215220f80a".lower(),
        "NEG_RISK_ADAPTER": "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296".lower(),
        "FEE_MODULE": "0x56C79347e95530c01A2FC76E732f9566dA16E113".lower(),
        "NEG_RISK_FEE_MODULE": "0x78769D50Be1763ed1CA0D5E878D93f05aabff29e".lower(),
        "RELAY_HUB": "0xD216153c06E857cD7f72665E0aF1d7D82172F494".lower(),
        "CONDITIONAL_TOKENS": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045".lower()
    }

    # USDC transfer event signature
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    USDC_SENDER = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

    def __init__(self, api_key: str, clob_client: ClobClient, max_workers: int = 5):
        """
        Initialize WalletBacktest
        
        Args:
            api_key: Polygonscan API key
            clob_client: Initialized ClobClient instance
            max_workers: Maximum number of workers for parallel processing
        """
        self.api_key = api_key
        self.client = clob_client
        self.max_workers = max_workers
        
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('RPC_URL')))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        self.contract_abis = self._load_contract_abis()
        self.match_orders_signature = os.getenv('MATCH_ORDERS_SIGNATURE')
        if not self.match_orders_signature:
            raise ValueError("MATCH_ORDERS_SIGNATURE not set in .env file")
        if not self.match_orders_signature.startswith('0x'):
            self.match_orders_signature = '0x' + self.match_orders_signature

    def _load_contract_abis(self) -> dict:
        """Load all contract ABIs from assets folder"""
        contract_abis = {}
        contract_names = {
            "CTF_EXCHANGE": "CtfExchange",
            "NEG_RISK_CTF_EXCHANGE": "NegRiskCtfExchange",
            "NEG_RISK_ADAPTER": "NegRiskAdapter",
            "FEE_MODULE": "FeeModule",
            "NEG_RISK_FEE_MODULE": "NegRiskFeeModule"
        }
        
        try:
            for key, name in contract_names.items():
                abi_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "abi", f"{name}.json")
                with open(abi_path) as f:
                    contract_abis[key] = json.load(f)
        except Exception as e:
            print(f"Error loading contract ABI: {e}")
            raise
            
        return contract_abis

    def get_tx_by_hash(self, tx_hash: str) -> Optional[Dict]:
        """
        Get transaction data directly by hash from Polygonscan
        """
        base_url = "https://api.polygonscan.com/api"
        
        params = {
            'module': 'proxy',
            'action': 'eth_getTransactionByHash',
            'txhash': tx_hash,
            'apikey': self.api_key
        }
        
        proxies = {
            'http': 'http://localhost:15236',
            'https': 'http://localhost:15236'
        }
        
        try:
            response = requests.get(base_url, params=params, proxies=proxies)
            data = response.json()

            if data.get('result'):
                return data['result']
            else:
                print(f"Error getting tx {tx_hash}: {data.get('message', 'Unknown error')}")
                return None
                
        except Exception as e:
            print(f"Failed to get transaction {tx_hash}: {e}")
            return None

    def get_tx_by_hash_web3(self, tx_hash: str) -> Optional[Dict]:
        """
        Get transaction data by hash using Web3
        """
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            if tx and hasattr(tx, 'input') and isinstance(tx['input'], bytes):
                tx_dict = dict(tx)
                tx_dict['input'] = '0x' + tx['input'].hex()
            return tx_dict
        except Exception as e:
            print(f"Error getting transaction: {e}")
            return None

    def decode_input_data_web3(self, contract_name: str, input_data: str) -> Optional[Dict]:
        """
        Decode transaction input data using Web3
        """
        try:
            # Create contract instance
            contract = self.w3.eth.contract(abi=self.contract_abis[contract_name])
            
            # Decode input data
            decoded = contract.decode_function_input(input_data)
            
            # Extract function name and parameters
            func_name = decoded[0].fn_name
            params = decoded[1]
            
            return {
                'function_name': func_name,
                'parameters': params
            }
        except Exception as e:
            print(f"Error decoding input data: {e}")
            return None

    def _process_transfer(self, transfer: Dict, pbar: tqdm) -> Dict:
        """Process a single transfer by getting its full transaction data"""
        relay = False
        tx_hash = transfer['hash']
        if transfer['from'] == self.POLYMARKET_CONTRACTS['CONDITIONAL_TOKENS']:
            relay = True
        if not relay:
            tx_data = self.get_tx_by_hash_web3(tx_hash)
            if tx_data:
                transfer['input'] = tx_data.get('input', '')
                transfer['interacted_with'] = tx_data.get('to', '')
        else:
            transfer['interacted_with'] = self.POLYMARKET_CONTRACTS['RELAY_HUB']
        pbar.update(1)
        return transfer

    def download_transactions(self, address: str) -> list:
        """
        Download all ERC-20 token transfers and their corresponding transaction data
        
        Args:
            address: The address to get token transfers for
        """
        base_url = "https://api.polygonscan.com/api"
        
        params = {
            'module': 'account',
            'action': 'tokentx',
            'address': address,
            'startblock': 0,
            'endblock': 99999999,
            'sort': 'desc',
            'apikey': self.api_key
        }
        
        proxies = {
            'http': os.getenv('HTTP_PROXY'),
            'https': os.getenv('HTTP_PROXY')
        }
        
        try:
            # Get token transfers
            response = requests.get(base_url, params=params, proxies=proxies)
            data = response.json()

            if data['status'] == '1':  # Success
                # Filter transfers that interact with Polymarket contracts
                polymarket_addresses = [addr.lower() for addr in self.POLYMARKET_CONTRACTS.values()]
                transfers = [
                    tx for tx in data['result'] 
                    if tx['from'].lower() in polymarket_addresses or tx['to'].lower() in polymarket_addresses
                ]
                
                # Use ThreadPoolExecutor for parallel processing
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # Create a progress bar
                    pbar = tqdm(total=len(transfers), desc="Processing transfers")
                    
                    # Submit all transfers to thread pool
                    futures = [executor.submit(self._process_transfer, transfer, pbar) 
                             for transfer in transfers]
                    
                    # Get results as they complete
                    transfers = [future.result() for future in as_completed(futures)]
                    
                    pbar.close()
                
                return transfers
            else:
                print(f"Error: {data['message']}")
                return []
                
        except Exception as e:
            print(f"Failed to download transactions: {e}")
            return []

    def get_current_positions(self, address: str) -> List[Dict]:
        """
        Get current positions and their market prices
        """
        positions = []
        
        try:
            # Get all positions for the address
            position_data = get_position_all(address)
            
            # Calculate market price for each position
            for pos in position_data:
                token_id = pos['asset']
                size = float(pos['size'])
                positions.append({
                    'token_id': token_id,
                    'size': size,
                    'current_value': pos['currentValue'],
                })
        except Exception as e:
            print(f"Error getting positions: {e}")
        
        return positions

    def calculate_pnl_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate P&L and win rate for each token_id
        """
        stats = []
        total_realized_pnl = 0
        
        # Group by token_id
        for token_id, group in df.groupby('tokenId'):
            # Sort by timestamp
            group = group.sort_values('timeStamp')
            # Calculate running position and P&L
            total_cost = 0
            total_proceeds = 0

            for _, row in group.iterrows():     
                if int(row['side']) == 0:  # BUY
                    total_cost += row['value']
                else:  # SELL
                    total_proceeds += row['value']
            
            # Calculate metrics
            realized_pnl = total_proceeds - total_cost
            # Only add realized_pnl to total if this is a new token_id
            if not any(s['token_id'] == token_id for s in stats):
                total_realized_pnl += realized_pnl
            
            stats.append({
                'token_id': token_id,
                'realized_pnl': realized_pnl,
                'total_volume': total_cost + total_proceeds
            })
        
        # Convert stats to DataFrame for easier processing
        stats_df = pd.DataFrame(stats)
        
        if not stats_df.empty:
            # Calculate win rate based on final P&L
            total_tokens = len(stats_df)
            winning_tokens = len(stats_df[stats_df['realized_pnl'] > 0])
            win_rate = winning_tokens / total_tokens if total_tokens > 0 else 0
            
            # Add win_rate to all rows with the same token_id
            stats_df['win_rate'] = win_rate
            stats_df['total_realized_pnl'] = round(total_realized_pnl, 4)
        return stats_df

    def decode_transaction_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Decode transaction input data for all transactions in DataFrame
        """
        decoded_data = []
        for _, row in df.iterrows():
            to_address = row['interacted_with'].lower() if row['interacted_with'] else ''
            contract_name = None
            if to_address == self.POLYMARKET_CONTRACTS['RELAY_HUB']:
                continue
            
            # Find which Polymarket contract this transaction is for
            for name, addr in self.POLYMARKET_CONTRACTS.items():
                if addr == to_address:
                    contract_name = name
                    break
            
            if contract_name and row.get('input'):
                try:
                    # Remove '0x' prefix if present for consistent handling
                    input_data = row['input']
                    if input_data.startswith('0x'):
                        input_data = input_data[2:]
                    
                    # Get contract instance
                    contract = self.w3.eth.contract(abi=self.contract_abis[contract_name])
                    
                    # Get function signature (first 4 bytes / 8 characters of input)
                    func_signature = '0x' + input_data[:8]
                    
                    # Check if this is the specific function signature we're looking for
                    if func_signature.startswith(self.match_orders_signature):  # matchOrders methodID 0xd2539b37
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
                            print(f"Failed to decode input for tx {row['hash']}: {e}")
                            decoded_data.append({})
                    else:
                        print(f"Skipping non-target function signature: {func_signature}")
                        decoded_data.append({})
                        
                except Exception as e:
                    print(f"Failed to decode input for tx {row['hash']}: {e}")
                    decoded_data.append({})
            else:
                decoded_data.append({})
        
        # Add decoded data to DataFrame
        decoded_df = pd.DataFrame(decoded_data)
        return pd.concat([df, decoded_df], axis=1)

    def process_transactions(self, transactions: list, address: str) -> pd.DataFrame:
        """
        Process transactions and calculate statistics
        
        Args:
            transactions: List of transactions to process
            address: Address to calculate statistics for
        """
        # Convert to DataFrame
        df = pd.DataFrame(transactions)

        # Convert timestamp to datetime
        df['timeStamp'] = pd.to_datetime(df['timeStamp'].astype(int), unit='s')
        
        # Convert token value from wei to USDC (6 decimals)
        df['value'] = df['value'].astype(float) / 1e6
        
        # Convert gas price from wei to Gwei
        df['gasPrice'] = df['gasPrice'].astype(float) / 1e9
        
        # Calculate gas cost in MATIC
        df['gasCost'] = (df['gasPrice'] * df['gasUsed'].astype(float)) / 1e9
        
        # Decode transaction data
        df = self.decode_transaction_data(df)
        
        # Get current positions
        positions = self.get_current_positions(address)
        
        # Add current position info to rows with matching token_id
        df['current_position'] = df.apply(
            lambda row: next(
                (pos['size'] for pos in positions if str(pos['token_id']) == str(row.get('tokenId'))), 
                0
            ), 
            axis=1
        )
        df['current_value'] = df.apply(
            lambda row: next(
                (pos['current_value'] for pos in positions if str(pos['token_id']) == str(row.get('tokenId'))), 
                0
            ), 
            axis=1
        )
        
        # Calculate P&L statistics
        pnl_stats = self.calculate_pnl_stats(df)
        
        if not pnl_stats.empty:
            # Merge P&L stats back into main DataFrame
            df = df.merge(
                pnl_stats[['token_id', 'realized_pnl', 'win_rate', 'total_realized_pnl']],
                left_on='tokenId',
                right_on='token_id',
                how='left'
            )
        
        df['totalTrades'] = len(df)
        # Calculate total value by summing current_value across all tokenIds
        total_current_value = df.drop_duplicates('tokenId')['current_value'].sum()
        df['total_current_value'] = total_current_value
        total_pnl = df['total_current_value'][0] + df['total_realized_pnl'][0]
        df['total_pnl'] = round(total_pnl, 4)
        
        return df


    def save_to_csv(self, df: pd.DataFrame, output_file: str):
        """
        Save processed DataFrame to CSV with proper column names
        
        Args:
            df: DataFrame to save
            output_file: Output CSV file path
        """
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Select and rename columns
        columns = {
            'timeStamp': 'time',
            'current_position': 'currentPosition',
            'current_value': 'currentValue',
            'function_name': 'functionName',
            'realized_pnl': 'realized P&L',
            'win_rate': 'winRate',
            'total_realized_pnl': 'totalRealizedP&L',
            'total_pnl': 'totalP&L',
            'total_current_value': 'totalCurrentValue'
        }
        
        # Fill missing columns with empty values
        for col in columns.keys():
            if col not in df.columns:
                df[col] = ''
        
        df = df.rename(columns=columns)
        
        # Sort by timestamp
        df = df.sort_values('time', ascending=False)
        
        # Save to CSV
        df.to_csv(output_file, index=False)
        # print(f"\nSaved data to: {output_file}")
        
        # self._print_summary(df)

    def _print_summary(self, df: pd.DataFrame):
        """Print transaction and P&L summary"""
        print("\nSummary:")
        print(f"Total Transfers: {len(df)}")
        print(f"Date Range: {df['time'].min()} to {df['time'].max()}")
        
        incoming = df[df['side'] == 0]['value'].sum()
        outgoing = df[df['side'] == 1]['value'].sum()
        print(f"Total Incoming: {incoming:.2f} USDC, Outgoing: {outgoing:.2f} USDC")
        
        if 'totalRealizedP&L' in df.columns:
            total_pnl = df['totalRealizedP&L'].iloc[0]
            win_rate = df['winRate'].iloc[0] * 100
            print(f"Total Realized P&L: {float(total_pnl):.4f} USDC")
            print(f"Win Rate: {float(win_rate):.1f}%")
            print(f"Total P&L: {float(df['totalP&L'].iloc[0]):.4f} USDC")
