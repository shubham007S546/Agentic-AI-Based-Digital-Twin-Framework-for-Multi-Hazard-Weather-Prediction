import asyncio
import sys
sys.path.insert(0, '.')
from app.ml.inference.rainfall_lstm_live import predict_rainfall_lstm

async def main():
    for district in ["Mandi", "Kullu", "Chamba"]:
        result = await predict_rainfall_lstm(district)
        print(f"{district:10} -> {result}")

asyncio.run(main())
