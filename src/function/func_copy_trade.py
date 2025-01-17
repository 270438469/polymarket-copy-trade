import asyncio
import logging
import os

from decimal import Decimal
from typing import Dict
from _py_clob_client.client import ClobClient
from _py_clob_client.clob_types import ApiCreds, MarketOrderArgs, OrderArgs, OrderType, BalanceAllowanceParams, AssetType
from _py_clob_client.order_builder.constants import SELL as SIDE_SELL
from _py_clob_client.constants import POLYGON
from dotenv import load_dotenv

from utils.utils import get_target_position_size

# load_dotenv()

# Get configuration from environment
PRIVATE_KEY = os.getenv('PK')
creds = ApiCreds(
    api_key=os.getenv("CLOB_API_KEY"),
    api_secret=os.getenv("CLOB_SECRET"),
    api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
)
FUNDER_ADDRESS = os.getenv('FUNDER')
WS_URL = os.getenv('WS_URL')

# Test mode configuration
TEST_MIN_ORDER = float(os.getenv('TEST_MIN_ORDER'))
TEST_MAX_ORDER = float(os.getenv('TEST_MAX_ORDER'))
TEST_DELAY = float(os.getenv('TEST_DELAY'))

# Production mode configuration
PROD_MIN_ORDER = float(os.getenv('PROD_MIN_ORDER'))
PROD_MAX_ORDER = float(os.getenv('PROD_MAX_ORDER'))
PROD_DELAY = float(os.getenv('PROD_DELAY'))

if not all([PRIVATE_KEY, FUNDER_ADDRESS, WS_URL]):
    raise ValueError("Missing required environment variables")

logger = logging.getLogger(__name__)


class PolymarketTrader:
    def __init__(self, mode: str = 'prod'):
        """
        Args:
            mode: 'test' for test mode, 'prod' for production mode
        """
        self.mode = mode
        self.min_order = TEST_MIN_ORDER if mode == 'test' else PROD_MIN_ORDER
        self.max_order = TEST_MAX_ORDER if mode == 'test' else PROD_MAX_ORDER
        self.delay = TEST_DELAY if mode == 'test' else PROD_DELAY
        
        self.client = ClobClient(
            host="https://clob.polymarket.com",
            key=os.getenv('PK'), 
            chain_id=POLYGON,
            creds=creds
        )

    def check_cash_balance(self):
        """Fetch USDC balance using web3"""
        try:
            balance_info = self.client.get_balance_allowance(
                    params=BalanceAllowanceParams(
                        asset_type=AssetType.COLLATERAL
                            )
                )
            return balance_info
            
        except Exception as e:
            logger.error(f"Failed to query balance: {e}")
            return None

    async def place_order(self, token_id: str, direction: str, amount: float) -> Dict:
        """
        Place an order with specified parameters
        
        Args:
            token_id: Market identifier
            direction: Order direction (BUY/SELL)
            amount: Order amount (USDC amount for BUY, position proportion for SELL)
        """
        try:
            if direction == "BUY":
                balance_info = self.check_cash_balance()
                if balance_info is None:
                    logger.error("Unable to get balance info, exiting trade")
                    return

                balance = float(balance_info['balance'])
                if balance < amount:
                    logger.error(f"Insufficient balance: current balance: {balance}, required: {amount}")
                    return
            else:   
                position_size = get_target_position_size(os.getenv('PUBKEY'), token_id)
                if position_size < amount:
                    logger.error(f"Insufficient position size: current position size: {position_size}, required: {amount}")
                    return

            # create a market order
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=direction
            )
            signed_order = self.client.create_market_order(order_args)
            response = self.client.post_order(signed_order)
            
            logger.info(f"{direction} Order placed successfully: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to place order: {str(e)}")
            raise

    async def execute_trade(self, trade_data: Dict):
        """
        Follow a trade with configured parameters
        """
        try:
            # Add delay before following trade
            await asyncio.sleep(self.delay)
            
            # Extract trade details
            token_id = trade_data.get("tokenId")
            side = trade_data.get("side")
            makerAmount = Decimal(str(trade_data.get("makerAmount", 0)))
            
            # Validate trade parameters
            if not all([token_id, side, makerAmount]):
                logger.error("Invalid trade data received")
                return
                
            # Apply size limits
            makerAmount = min(max(makerAmount, Decimal(str(self.min_order))), Decimal(str(self.max_order)))
            
            # Place the market order
            order_response = await self.place_order(
                token_id=token_id,
                direction=side,
                amount=float(makerAmount)
            )
            
            logger.info(f"Market order placed successfully: {order_response}")
            
        except Exception as e:
            logger.error(f"Error following trade: {str(e)}")

    async def close(self):
        """
        Clean up resources
        """ 
        if self.client:
            await self.client.close() 

