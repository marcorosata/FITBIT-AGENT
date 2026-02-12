"""Quick WebSocket test — checks if data is streaming from the server."""

import asyncio
import json
import sys

async def test_ws(uri: str, label: str, timeout: int = 15):
    try:
        import websockets
    except ImportError:
        print("Installing websockets...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets

    print(f"\n{'='*60}")
    print(f"Testing: {label}")
    print(f"URI: {uri}")
    print(f"{'='*60}")

    try:
        async with websockets.connect(uri, close_timeout=5) as ws:
            print(f"  ✅ Connected!")
            count = 0
            try:
                while count < 5:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    data = json.loads(msg)
                    msg_type = data.get("type", "unknown")
                    count += 1

                    if msg_type == "reading":
                        payload = data.get("data", {})
                        print(f"  📊 [{count}] Reading: {payload.get('metric_type', '?')} = {payload.get('value', '?')} "
                              f"(participant: {payload.get('participant_id', '?')[:12]}...)")
                    elif msg_type == "alert":
                        payload = data.get("data", {})
                        print(f"  🚨 [{count}] Alert: {payload.get('message', '?')[:80]}")
                    else:
                        print(f"  📨 [{count}] {msg_type}: {str(data)[:200]}")

            except asyncio.TimeoutError:
                if count == 0:
                    print(f"  ⚠️  No messages received in {timeout}s — server may not be streaming data")
                else:
                    print(f"  ⏱️  No more messages after {count} received")

            print(f"  Total messages received: {count}")

    except Exception as e:
        print(f"  ❌ Connection error: {e}")


async def main():
    # Test Railway production server
    await test_ws(
        "wss://fitbit-agent-production.up.railway.app/ws/stream?channel=all",
        "Railway Production Server"
    )

    # Test local server
    await test_ws(
        "ws://localhost:8000/ws/stream?channel=all",
        "Local Server (localhost:8000)"
    )


if __name__ == "__main__":
    asyncio.run(main())
