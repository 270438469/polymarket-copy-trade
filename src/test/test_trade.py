import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.function.func_copy_trade import PolymarketTrader

# Set proxy first
# os.environ['HTTP_PROXY'] = os.getenv('HTTP_PROXY')
# os.environ['HTTPS_PROXY'] = os.getenv('HTTPS_PROXY')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    # Initialize trader
    trader = PolymarketTrader()
    
    try:
        # Get market details from environment
        token_id = int(os.getenv('TEST_TOKEN_ID'))
        amount = int(os.getenv('TEST_ORDER_AMOUNT'))
        
        logger.info(f"Testing trade for market {token_id} with amount {amount}")
        
        # Create and submit orders
        await trader.place_order(
            token_id=token_id,
            side=0,  # BUY:0, SELL:1
            amount=amount
        )
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program stopped by user")
