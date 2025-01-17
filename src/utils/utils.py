import requests


def get_target_position_size(address, token_id): 
    """
    returns size in shares
    """
    url = f'https://data-api.polymarket.com/positions?user={address}&sizeThreshold=.1&limit=50&offset=0&sortBy=CURRENT&sortDirection=DESC'
    with requests.Session() as session: 
        response = session.get(url)
        data = response.json()
    for position in data: 
        if position['asset'] == token_id: 
            return position['size']
    return 0

def get_position_all(address): 
    """
    returns size in shares
    """
    url = f'https://data-api.polymarket.com/positions?user={address}&sizeThreshold=.1&limit=50&offset=0&sortBy=CURRENT&sortDirection=DESC'
    with requests.Session() as session: 
        response = session.get(url)
        data = response.json()
        return data