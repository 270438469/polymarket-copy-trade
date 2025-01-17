from decimal import Decimal
from typing import Union, Dict


def format_decimal(value: Union[int, float, str, Decimal]) -> Decimal:
    """
    Format a number as Decimal with proper precision
    """
    return Decimal(str(value))


def calculate_slippage_price(
    base_price: Decimal,
    slippage: Decimal,
    is_buy: bool
) -> Decimal:
    """
    Calculate price adjusted for slippage
    """
    if is_buy:
        return base_price * (1 + slippage)
    return base_price * (1 - slippage)


def validate_trade_data(trade_data: Dict) -> bool:
    """
    Validate trade data contains all required fields
    """
    required_fields = ['marketId', 'side', 'price', 'size']
    return all(field in trade_data for field in required_fields)


def format_log_message(message: str, data: Dict = None) -> str:
    """
    Format log message with optional data
    """
    if data:
        return f"{message} - {data}"
    return message 