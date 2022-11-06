import os
import sys
from math import fabs
from typing import TypeVar
import requests
from datetime import datetime
import json

API_KEY = os.environ.get('TOS_API_KEY')
GENERATED_ORDER_FILE_PATH = os.environ.get('TOS_GEN_ORDER_FILE_PATH')
ticker = '$SPX.X'


def is_prime(n):
    for i in range(2, n):
        if (n % i) == 0:
            return False
    return True


# TOS API call to get OTM option type (Call/Put)
def tos_get_option_chain(ticker_symbol: str, contractType='ALL', rangeType='OTM', apiKey=None):
    if apiKey is None:
        raise ValueError("TOS Option API Key is not defined.")

    # Price History
    endpoint = 'https://api.tdameritrade.com/v1/marketdata/chains'

    payload = {'apikey': apiKey,
               'symbol': ticker_symbol,
               'contractType': contractType,  # Values: CALL, PUT, ALL*
               'strikeCount': None,
               'strategy': 'SINGLE',
               # Values: SINGLE, ANALYTICAL, COVERED, VERTICAL, CALENDAR, STRANGLE, STRADDLE, BUTTERFLY, CONDOR, DIAGONAL, COLLAR, ROLL
               'range': rangeType,
               # Values: ITM, NTM (Near-the-money), OTM, SAK (Strikes Above Market), SBK (Strikes Below Market), SNK (Strikes Near Market), ALL (All Strikes)
               'fromDate': None,  # Values: Valid ISO-8601 formats are: yyyy-MM-dd and yyyy-MM-dd'T'HH:mm:ssz.'
               'toDate': None,  # Values: Valid ISO-8601 formats are: yyyy-MM-dd and yyyy-MM-dd'T'HH:mm:ssz.'
               'expMonth': 'ALL',
               # Values: (frequencyType = 'minute') 1*, 5, 10, 15, 30, (frequencyType = 'daily') 1*, (frequencyType = 'weekly') 1*, (frequencyType = 'monthly') 1*
               'optionType': 'ALL'  # Values: S (Standard contracts), NS (Non-standard contracts), ALL (All contracts)
               }

    # Make a request
    content = requests.get(url=endpoint, params=payload)

    return content.json()


T = TypeVar('T')
def find_best_match(input: T, key_type: str, insert=None):
    best_match_list = []
    best_input_match = input
    best_input_match_diff = sys.maxsize
    for i in insert:
        for x in i:
            if x == key_type:
                if abs(i[x] - input) < best_input_match_diff:
                    best_input_match_diff = abs(i[x] - input)
                    best_input_match = i[x]
    for i in insert:
        for x in i:
            if x == key_type:
                if i[x] == best_input_match:
                    best_match_list.append(i)

    return best_match_list


def filter_data(input_option_type: str, input_dte: int, input_delta: float, input_quantity: int, json_data_in=None):
    insert = []
    current_date = datetime.now()

    for option_chain_type in ['call', 'put']:
        for exp_date in json_data_in[f'{option_chain_type}ExpDateMap'].values():
            for strike in exp_date.values():

                expiry_date = datetime.fromtimestamp(strike[0]["expirationDate"] / 1000.0)
                option_type = strike[0]['putCall']
                strike_price = strike[0]['strikePrice']
                description = strike[0]['description']
                mark = strike[0]['mark']
                delta_val = strike[0]['delta']

                absolute_delta = fabs(float(delta_val) * 100)
                day_diff = (expiry_date - current_date).days
                if input_option_type != option_type or delta_val == -999.0:
                    continue

                option_chain_row = {"ticker": ticker,
                                    "expiry_date": expiry_date,
                                    "options_type": option_type,
                                    "strike_price": strike_price,
                                    "description": description,
                                    "mark": mark,
                                    "quantity": input_quantity,
                                    "day_diff": day_diff,
                                    "absolute_delta": absolute_delta}

                insert.append(option_chain_row)

    filtered_list_step1 = find_best_match(input_dte, "day_diff", insert)
    filtered_list_step2 = find_best_match(input_delta, "absolute_delta", filtered_list_step1)

    return filtered_list_step2


user_done = False
additional_run = False

while not user_done:
    input_trade_name = input('Enter trade name (type m for menu, q to quit): ')

    f = open('trade_structures.json')
    trade_structure_defs = json.load(f)

    if input_trade_name == 'm' or input_trade_name == 'M':
        print("\nTrade Menu:")
        for i in trade_structure_defs['trade_structures']:
            print(i['trade_name'])
        print("\n")
        f.close()
        continue
    elif input_trade_name == 'q' or input_trade_name == 'Q':
        f.close()
        quit()

    json_data = tos_get_option_chain(ticker, contractType='ALL', rangeType='ALL', apiKey=API_KEY)
    # Sometimes the option chain data retrieval fails for some reason (TDA server error?)
    # So, keep trying until we get good data.
    for option_chain_type in ['call', 'put']:
        while len(json_data[f'{option_chain_type}ExpDateMap'].values()) == 0:
            json_data = tos_get_option_chain(ticker, contractType='ALL', rangeType='ALL', apiKey=API_KEY)

    good_data = False
    for option_chain_type in ['call', 'put']:
        for exp_date in json_data[f'{option_chain_type}ExpDateMap'].values():
            for strike in exp_date.values():
                delta_val = strike[0]['delta']
                if delta_val == -999:
                    continue
                else:
                    good_data = True

    if not good_data:
        print("\nWarning - Bad option data from TDA's API detected. Please try again later.\n")
        additional_run = True
    else:
        file_mode = 'w'
        if additional_run:
            file_mode = 'a'
        f = open(str(GENERATED_ORDER_FILE_PATH) + 'TOS_order_gen.txt', file_mode)

        print("\n")
        trade_found = False
        for i in trade_structure_defs['trade_structures']:
            if i['trade_name'] == input_trade_name or i['trade_name'].lower() == input_trade_name:
                trade_found = True
                print("The following order was written to the file:")
                for j in i['trade_components']:
                    option_data_list = []
                    number_of_trades = 0
                    tranche_string = ""
                    option_type: str
                    dte = 0
                    delta: float
                    buy_or_sell_string = ""
                    exp_date_string = ""
                    strike_string = ""
                    put_or_call_string = ""
                    exp_type_suffix = ""
                    exp_type_prefix = ""
                    counter = 0
                    min_quantity = sys.maxsize

                    for k in j['legs']:

                        option_type = k['option_type']
                        dte = k['dte']
                        delta = k['delta']

                        option_data_list.append(filter_data(option_type, dte, delta, k['quantity'], json_data))

                        if abs(k['quantity']) < min_quantity:
                            min_quantity = abs(k['quantity'])
                        counter += 1

                    if not is_prime(min_quantity):
                        number_of_trades = min_quantity
                    else:
                        number_of_trades = 1

                    for k in j['legs']:
                        tranche_string += str(int(k['quantity'] / number_of_trades))
                        if k['leg_id'] < j['number_of_legs'] - 1:
                            tranche_string += '/'

                    sum_credit_debit = 0.0
                    counter = 0
                    for x in option_data_list:
                        # There's a bug in filter_data where sometimes multiple strikes are chosen in leg.
                        # This is a Band-aid to remove all but the first in the list.
                        while len(x) > 1:
                            x.pop(1)
                        for y in x:
                            sum_credit_debit += (y['quantity'] * y['mark'])

                            if "AM" in y['description'] and "SPX " in y['description']:
                                exp_type_prefix = ""
                                exp_type_suffix = " [AM]"
                            elif "PM" in y['description'] and 'Quarterly' in y['description']:
                                exp_type_prefix = "(Quarterlys)"
                                exp_type_suffix = ""
                            elif "PM" in y['description'] and 'Quarterly' not in y['description'] and "SPXW " in y[
                                'description']:
                                exp_type_prefix = "(Weeklys)"
                                exp_type_suffix = ""
                            else:
                                exp_type_prefix = "unhandled"
                                exp_type_suffix = "unhandled"

                            exp_date_string += y['expiry_date'].strftime('%d ') + \
                                               y['expiry_date'].strftime('%b ').upper() + \
                                               y['expiry_date'].strftime('%y') + exp_type_suffix
                            strike_string += str(int(y['strike_price']))
                            put_or_call_string += str(y['options_type'])
                            if counter < j['number_of_legs'] - 1:
                                exp_date_string += '/'
                                strike_string += '/'
                                put_or_call_string += '/'
                        counter += 1
                    if sum_credit_debit < 0.0:
                        buy_or_sell_string = "SELL"
                    else:
                        buy_or_sell_string = "BUY"

                    print(buy_or_sell_string + " +" + str(number_of_trades) + " " + tranche_string +
                          " CUSTOM SPX 100 " + exp_type_prefix + " " + exp_date_string + " " + strike_string + " " + put_or_call_string +
                          " @ LMT")
                    f.write(buy_or_sell_string + " +" + str(number_of_trades) + " " + tranche_string +
                            " CUSTOM SPX 100 " + exp_type_prefix + " " + exp_date_string + " " + strike_string + " " + put_or_call_string +
                            " @ LMT\n")

        f.close()

        if not trade_found:
            print("Trade not found in trade_structures file. Please try again.\n")
            additional_run = True
        else:
            input_valid = False
            while not input_valid:
                user_continues = input('\nAdd another trade [y/n]? ')
                if user_continues == 'n' or user_continues == 'N':
                    user_done = True
                    input_valid = True
                elif user_continues == 'y' or user_continues == 'Y':
                    additional_run = True
                    input_valid = True
                else:
                    print("Unhandled input entered. Please try again.")
