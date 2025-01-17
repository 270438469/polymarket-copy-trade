import asyncio
import logging
import sys
import os
from typing import Dict

from function.func_monitor import WalletMonitor
from function.func_copy_trade import PolymarketTrader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('polymarket_follower.log')
    ]
)

logger = logging.getLogger(__name__)

# Main application class for following trades on Polymarket
class PolymarketFollower:
    def __init__(self):
        self.trader = PolymarketTrader()
        self.monitor = WalletMonitor(self.handle_trade)
        
    # Handle trades from monitored wallet
    async def handle_trade(self, trade_data: Dict):
        """
        params:
            trade_data: Trade data from the monitored wallet
        """
        logger.info(f"New trade detected: {trade_data}")
        await self.trader.execute_trade(trade_data)
        
    # Start the application
    async def start(self):
        try:  
            # Initialize trader
            await self.trader.initialize()
            
            # Start monitoring
            logger.info("Starting wallet monitor...")
            await self.monitor.start()
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Application error: {str(e)}")
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Clean up resources."""
        await self.monitor.stop()
        await self.trader.close()


async def main():
    app = PolymarketFollower()
    await app.start()


if __name__ == "__main__":
    os.environ['HTTP_PROXY'] = os.getenv('HTTP_PROXY')
    os.environ['HTTPS_PROXY'] = os.getenv('HTTPS_PROXY')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")