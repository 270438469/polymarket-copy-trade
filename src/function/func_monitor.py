import asyncio
import json
import logging
import os
from typing import Callable, Dict, Optional
from dotenv import load_dotenv

import websockets
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_abi import decode, encode
from eth_abi.codec import ABICodec
from eth_abi.registry import registry

load_dotenv()

logger = logging.getLogger(__name__)


class WalletMonitor:
    def __init__(self, on_trade_callback: Callable, mode: str = 'prod'):
        """
        params:
            on_trade_callback: Callback function to handle detected trades
            mode: 'test' for test wallet, 'prod' for target wallet (default: 'prod')
        """
        # Select wallet based on mode
        wallet_env_var = 'TEST_WALLET' if mode == 'test' else 'TARGET_WALLET'
        wallet_address = os.getenv(wallet_env_var)
        
        self.target_wallet = Web3.to_checksum_address(wallet_address)
        logger.info(f"Monitoring in {mode} mode for wallet: {self.target_wallet}")
        
        # Use Polygon WebSocket URL
        self.ws_url = os.getenv('WS_URL')
        self.web3 = Web3(Web3.WebsocketProvider(self.ws_url))
        # Add PoS middleware
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.on_trade_callback = on_trade_callback
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.message_count = 0
        
        # Get matchOrders signature from env
        self.match_orders_signature = os.getenv('MATCH_ORDERS_SIGNATURE')
        if not self.match_orders_signature:
            raise ValueError("MATCH_ORDERS_SIGNATURE not set in .env file")
        if not self.match_orders_signature.startswith('0x'):
            self.match_orders_signature = '0x' + self.match_orders_signature
        
        # Load contract ABI
        try:
            abi_path = os.path.join(os.path.dirname(__file__), '..', 'asset/abi', 'NegRiskFeeModule.json')  # same MATCH_ORDERS_SIGNATURE in NegRiskFeeModule.json & FeeModule.json
            logger.info(f"Loading ABI from: {abi_path}")
            
            with open(abi_path, 'r') as f:
                self.contract_abi = json.load(f)
                
                # Find matchOrders function ABI
                self.match_orders_abi = next(
                    (item for item in self.contract_abi 
                    if item.get('type') == 'function' and item.get('name') == 'matchOrders'),
                    None
                )
                
                if self.match_orders_abi is None:
                    raise ValueError("matchOrders function not found in ABI")
                
        except Exception as e:
            logger.error(f"Error loading ABI: {str(e)}")
            raise

    # Decode input data
    def decode_match_orders(self, input_data: str) -> Optional[Dict]:
        """Decode matchOrders function input data"""
        try:
            # Create contract function object
            contract = self.web3.eth.contract(
                abi=[self.match_orders_abi]
            )
            
            # Decode parameters
            decoded = contract.decode_function_input(input_data)
            # logger.info(f"Decoded parameters: {decoded}")
            
            # decoded is a tuple of (function_name, parameters)
            _, params = decoded
            taker_order = params['takerOrder']
            
            return {
                "maker": taker_order['maker'],
                "makerAmount": taker_order['makerAmount'],
                "tokenId": taker_order['tokenId'],
                "side": taker_order['side']
            }
            
        except Exception as e:
            logger.debug(f"Error decoding matchOrders data: {str(e)}")
            return None

    # Process incoming WebSocket message
    async def process_message(self, message: str):
        """
        params:
            message: Raw WebSocket message
        """
        try:
            data = json.loads(message)
            if "params" in data and "result" in data["params"]:
                tx_data = data["params"]["result"]
                tx_hash = tx_data.get("hash", "unknown")
                input_data = tx_data.get("input", "")
                
                # Check if matchOrders call
                if input_data.startswith(self.match_orders_signature):
                    logger.info(f"MatchOrders TX detected: {tx_hash}")
                    decoded_data = self.decode_match_orders(input_data)
                    # logger.info(f"Decoded data: {decoded_data}")
                    
                    if decoded_data and decoded_data["maker"].lower() == self.target_wallet.lower():
                        logger.info(f"""
                            Target wallet matchOrders detected:
                            TX Hash: {tx_hash}
                            Maker: {decoded_data["maker"]}
                            Maker Amount: {decoded_data["makerAmount"]}
                            Token ID: {decoded_data["tokenId"]}
                            Side: {"BUY" if decoded_data["side"] == 0 else "SELL"}
                        """)
                        await self.on_trade_callback(decoded_data)
                    else:
                        logger.debug(f"MatchOrders TX detected (not target): {tx_hash}")
                    
        except json.JSONDecodeError:
            logger.error(f"Failed to decode WebSocket message: {message}")
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")

    # Get current block height from Polygon
    async def get_block_height(self):
        """Get current block height from Polygon network"""
        try:
            block_number = self.web3.eth.block_number
            return block_number
        except Exception as e:
            logger.error(f"Error getting block height: {str(e)}")
            return None

    # Monitor and log block height
    async def monitor_block_height(self):
        """Monitor and log block height every 5 seconds"""
        while self.running:
            try:
                block_height = await self.get_block_height()
                if block_height:
                    logger.info(f"Current block height: {block_height} | Messages received: {self.message_count}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error in block height monitor: {str(e)}")
                await asyncio.sleep(5)

    # Start monitoring
    async def start(self):
        self.running = True
        # Start block height monitoring in a separate task
        asyncio.create_task(self.monitor_block_height())
        
        while self.running:
            try:
                logger.info(f"Connecting to Polygon WebSocket at {self.ws_url}")
                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    
                    # Subscribe to all pending transactions
                    subscribe_message = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["alchemy_pendingTransactions"]
                    }
                    
                    await websocket.send(json.dumps(subscribe_message))
                    subscription_response = await websocket.recv()
                    logger.info(f"Subscription response: {subscription_response}")
                    
                    # Process incoming messages
                    while self.running:
                        message = await websocket.recv()
                        self.message_count += 1
                        await self.process_message(message)
                        
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed. Reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error in wallet monitor: {str(e)}")
                await asyncio.sleep(5)

    # Stop monitoring
    async def stop(self):
        self.running = False
        if self.websocket:
            await self.websocket.close() 