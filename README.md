# 🤖 Polymarket one-stop Copy Trading Bot

A Python-based trading bot that follows and replicates trades from specified wallets on Polymarket. It also includes backtesting tools to identify and validate profitable wallets before copy trading.

## ⚙️ Requirements

- Python 3.8+
- Polygon Network wallet with USDC
- Polygon RPC endpoint

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/polymarket-copy-trade.git
cd polymarket-copy-trade
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```
Edit `.env` with your configuration.

## 📝 Usage

### Main Functions

- Copy trading from target wallet:
```bash
python src/main_copy_trade.py
```

- Backtest wallet trading history:
```bash
python src/main_backtest.py
```

### Test Functions

The `src/test` directory contains individual test files for specific functionalities:

- `test_trade.py`: Test trade
- `test_monitor.py`: Test monitor

## 🔧 Modifications

- Enhanced `_py_clob_client` with additional features:
  - Modified `create_market_order` functionality
  - Modified order amount calculations for both BUY/SELL sides
  - Improved transaction data decoding

## ⚠️ Disclaimer

This bot is for educational purposes only. Use at your own risk. Trading cryptocurrency carries significant risks. 

## 📝 TODO
 - effectively searching for smart wallet and build pools
 - periodically backtesting 
