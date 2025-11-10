import time
import csv
from datetime import datetime
from statistics import fmean

import requests
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
from colorama import init, Fore, Style
import matplotlib.pyplot as plt

version = 1.1
print("Krypto-Sentinel by sailedship. Version:", version)
init(autoreset=True)
datetime_at_start=datetime.now()
symbol = input("Enter a 3-letter cryptocurrency code in capital letters e.g. BTC for Bitcoin, ETH for Ethereum, SOL for Solana, BNB for Build and Build (Binance) ").upper()
answer = input("Would you like to save data from different instances in different files or same files? Type D for different files. Type S for same files.")
if answer == 'D':
    print("Preference saved")
    csv_file = f"{symbol.lower()}_prices_starting_from{datetime.now().strftime('%Y-%m-%d')}.csv"
if answer == 'S':
    print("Preference saved")
    csv_file = f"{symbol.lower()}_prices.csv"
print(f"\nTracking {symbol} to USD...")

try:
    with open(csv_file, 'x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Timestamp',
            f'{symbol} Price (USD)',
            'Price Change Summary',
            'Market Gist',
            'Detected Pattern',
            'Accuracy (%)',
            'Forecast Direction',
            'Forecast Target Price (USD)',
            'RSI',
            'EMA(12)',
            'EMA(26)'
        ])
except FileExistsError:
    pass

price_history = []
predictions = []
correct_predictions = 0
total_predictions = 0


def compute_ema(prices, period):
    if not prices:
        return 0
    if len(prices) < period:
        return fmean(prices)

    ema = fmean(prices[:period])
    multiplier = 2 / (period + 1)
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def compute_rsi(prices, period=14):
    if len(prices) <= period:
        return 50.0

    recent = prices[-(period + 1):]
    gains = []
    losses = []
    for i in range(1, len(recent)):
        change = recent[i] - recent[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    average_gain = fmean(gains) if any(gains) else 0
    average_loss = fmean(losses) if any(losses) else 0

    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def build_forecast(prices, pattern):
    ema_short = compute_ema(prices, 12)
    ema_long = compute_ema(prices, 26)
    rsi = compute_rsi(prices)

    last_price = prices[-1]
    trend_bias = ema_short - ema_long
    normalized_bias = trend_bias / last_price if last_price else 0

    if trend_bias > 0:
        direction = "Bullish"
    elif trend_bias < 0:
        direction = "Bearish"
    else:
        direction = "Neutral"

    if rsi >= 70:
        rsi_signal = "Overbought"
        if direction == "Bullish":
            direction = "Neutral"
    elif rsi <= 30:
        rsi_signal = "Oversold"
        if direction == "Bearish":
            direction = "Neutral"
    else:
        rsi_signal = "Balanced"

    confidence = min(0.95, max(0.15, abs(normalized_bias) * 12))
    if direction == "Neutral":
        confidence = min(confidence, 0.45)

    if "Bullish" in pattern and direction != "Bearish":
        direction = "Bullish"
        confidence = max(confidence, 0.6)
    elif "Bearish" in pattern and direction != "Bullish":
        direction = "Bearish"
        confidence = max(confidence, 0.6)

    if direction == "Bullish":
        predicted_change_pct = max(0.001, abs(normalized_bias))
    elif direction == "Bearish":
        predicted_change_pct = -max(0.001, abs(normalized_bias))
    else:
        predicted_change_pct = 0

    target_price = last_price * (1 + predicted_change_pct)

    rationale_parts = [
        f"EMA(12)={ema_short:.2f}",
        f"EMA(26)={ema_long:.2f}",
        f"RSI({rsi_signal})={rsi:.1f}"
    ]
    if pattern != "No Pattern":
        rationale_parts.append(f"Pattern={pattern}")

    forecast_summary = "; ".join(rationale_parts)

    return {
        "direction": direction,
        "confidence": confidence,
        "target_price": target_price,
        "ema_short": ema_short,
        "ema_long": ema_long,
        "rsi": rsi,
        "rationale": forecast_summary,
    }


def detect_pattern(price_history):
    if len(price_history) < 100:
        return "No Pattern"
    p = price_history[-100:]
    if p[-5] < p[-4] < p[-3] < p[-2] < p[-1]:
        return "Ascending Triangle / Bullish"
    elif p[-5] > p[-4] > p[-3] > p[-2] > p[-1]:
        return "Descending Triangle / Bearish"
    elif p[-5] < p[-4] > p[-3] < p[-2] > p[-1]:
        return "Triple Top / Bearish"
    elif p[-5] > p[-4] < p[-3] > p[-2] < p[-1]:
        return "Triple Bottom / Bullish"
    elif p[-4] < p[-5] and p[-4] < p[-3] and p[-2] > p[-3] and p[-1] < p[-2]:
        return "Head and Shoulders / Bearish"
    elif p[-4] > p[-5] and p[-4] > p[-3] and p[-2] < p[-3] and p[-1] > p[-2]:
        return "Inverted Head and Shoulders / Bullish"
    elif (p[-5] < p[-4] and p[-3] < p[-4] and p[-3] > p[-2] and p[-2] < p[-1]):
        return "Double Bottom / Bullish"
    elif (p[-5] > p[-4] and p[-3] > p[-4] and p[-3] < p[-2] and p[-2] > p[-1]):
        return "Double Top / Bearish"
    elif abs(p[-5] - p[-1]) < 0.2 * p[-5] and (max(p[-5:]) - min(p[-5:])) > 0.05 * p[-5]:
        return "Symmetrical Triangle / Neutral"
    return "No Pattern"

plt.ion()
fig, ax = plt.subplots(figsize=(8, 4))

while True:
    print(f"\nStarting request for {symbol}...")

    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    parameters = {
        'symbol': symbol,
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'Accept-Encoding': 'deflate, gzip',
        'X-CMC_PRO_API_KEY': 'INSERT API KEY HERE',  # Reminder to insert api key
    }

    try:
        response = requests.get(url, headers=headers, params=parameters, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = data['data'][symbol]['quote']['USD']['price']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"{timestamp} - {symbol} Price: ${price:.2f}")
        price_history.append(price)
        if len(price_history) > 100:
            price_history.pop(0)

        if len(predictions) > 0:
            prev_prediction, prev_price = predictions.pop(0)
            actual_change = price - prev_price
            if prev_prediction in ("Bullish", "Bearish"):
                if (prev_prediction == "Bullish" and actual_change > 0) or (
                    prev_prediction == "Bearish" and actual_change < 0
                ):
                    correct_predictions += 1
                total_predictions += 1

        if len(price_history) >= 30:
            differences = [price_history[i + 1] - price_history[i] for i in range(len(price_history) - 1)]
            recent_differences = differences[-10:]
            diff_strings = ["{:+.2f}".format(d) for d in recent_differences]
            positive_count = sum(1 for d in recent_differences if d > 0)
            if positive_count >= 6:
                market_gist = "Bullish"
            elif positive_count <= 3:
                market_gist = "Bearish"
            else:
                weights = list(range(1, len(recent_differences) + 1))
                weighted_sum = sum(weights[i] * recent_differences[i] for i in range(len(recent_differences)))
                market_gist = "Bullish" if weighted_sum > 0 else "Bearish"

            pattern = detect_pattern(price_history)
            if "Bullish" in pattern:
                market_gist += " + Pattern Bullish Influence"
            elif "Bearish" in pattern:
                market_gist += " + Pattern Bearish Influence"

            forecast = build_forecast(price_history, pattern)
            if forecast["direction"] in ("Bullish", "Bearish"):
                predictions.append((forecast["direction"], price))
            accuracy = (correct_predictions / total_predictions * 100) if total_predictions else 0
            accuracy_str = f"{accuracy:.2f}%"
            total_change = sum(recent_differences)
            print("Correct Predictions:", correct_predictions)
            wrong_predictions = total_predictions - correct_predictions
            print("Wrong Predictions:", wrong_predictions)

            if market_gist.startswith("Bullish"):
                color = Fore.GREEN
            elif market_gist.startswith("Bearish"):
                color = Fore.RED
            else:
                color = Fore.BLUE
            print(f"Recent price differences: {', '.join(diff_strings)}")
            print(color + f"Market Gist: {market_gist} ({total_change:+.2f})")
            print(Fore.YELLOW + f"Detected Pattern: {pattern}")
            print(Fore.CYAN + f"Prediction Accuracy: {accuracy_str}")
            print(
                Fore.MAGENTA
                + f"Forecast: {forecast['direction']} -> ${forecast['target_price']:.2f}"
                + f" (confidence {(forecast['confidence'] * 100):.1f}%)"
            )
            print(Fore.BLUE + f"Indicators: {forecast['rationale']}")
            print(Style.RESET_ALL + "-" * 40)

            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp,
                    f"{price:.2f}",
                    ' / '.join(diff_strings),
                    f"{market_gist} ({total_change:+.2f})",
                    pattern,
                    accuracy_str,
                    forecast['direction'],
                    f"{forecast['target_price']:.2f}",
                    f"{forecast['rsi']:.2f}",
                    f"{forecast['ema_short']:.2f}",
                    f"{forecast['ema_long']:.2f}"
                ])

            ax.clear()
            visible_history = price_history[-30:]
            ax.plot(range(len(visible_history)), visible_history, marker='o', linestyle='-', color='red', label='Price')
            if forecast["direction"] in ("Bullish", "Bearish"):
                target_color = 'green' if forecast["direction"] == "Bullish" else 'red'
                ax.axhline(
                    forecast["target_price"],
                    color=target_color,
                    linestyle='--',
                    linewidth=1.5,
                    label=f"Forecast Target ({forecast['direction']})"
                )
            ax.set_title(f"{symbol} Price History - Last {len(visible_history)} Points\nPattern: {pattern}")
            ax.set_xlabel("Point")
            ax.set_ylabel(f"{symbol} Price (USD)")
            ax.grid(True)
            ax.legend(loc='best')
            fig.tight_layout()
            fig.canvas.draw()
            plt.pause(60)
        else:
            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, f"{price:.2f}", '', '', '', '', '', '', '', '', ''])
    except (ConnectionError, Timeout, TooManyRedirects) as e:
        print(Fore.RED + f"Request failed. Check Wi-Fi.: {e}")
    except requests.HTTPError as http_err:
        if response.status_code == 429:
            print(Fore.YELLOW + "Rate limit exceeded. Waiting 10 min...")
            time.sleep(60)
        else:
            print(Fore.RED + f"HTTP error occurred. Error code: {http_err}")
    except Exception as err:
        print(Fore.RED + f"An Error Occurred. Error code: {err}")
