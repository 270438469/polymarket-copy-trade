import asyncio
import logging
import os
import sys

from decimal import Decimal
from typing import Dict
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.function.func_monitor import WalletMonitor

# Set proxy first
os.environ['HTTP_PROXY'] = os.getenv('HTTP_PROXY')
os.environ['HTTPS_PROXY'] = os.getenv('HTTPS_PROXY')

# Load environment variables
# os.environ.clear()
# load_dotenv()

# Get test wallet from environment
TEST_WALLET = os.getenv('TEST_WALLET')
if not TEST_WALLET:
    raise ValueError("TEST_WALLET not set in .env file")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Callback to process trade details
async def handle_trade(trade_data: Dict):
    try:
        market_id = trade_data.get("tokenId", "Unknown TokenId")
        side = trade_data.get("side", "Unknown")
        maker = trade_data.get("maker", "Unknown")
        size = Decimal(str(trade_data.get("makerAmount", 0)))

        logger.info(f"""
            Trade Details:
            -------------
            Token ID: {market_id}
            Side: {side}
            Maker: {maker}
            Size: {size}
        """)
    except Exception as e:
        logger.error(f"Error processing trade details: {str(e)}")

async def main():
    # Create monitor instance with our callback and test wallet
    monitor = WalletMonitor(handle_trade, mode='test')
    
    try:
        logger.info(f"Started monitoring test wallet: {TEST_WALLET}")
        await monitor.start()
    except KeyboardInterrupt:
        logger.info("Stopping monitor...")
        await monitor.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program stopped by user")


