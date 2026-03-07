import asyncio
import json
import websockets
import sys


async def test_websocket():
    uri = "ws://localhost:8000/ws/chat?token=test-token"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to websocket.")

            # 1. Wait for 'connected' message
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Received: {data}")
            if data.get("type") != "connected":
                print(f"Error: Expected 'connected' type, got {data.get('type')}")
                return

            session_id = data.get("session_id")
            print(f"Session ID: {session_id}")

            # 2. Test Ping/Pong
            print("Sending ping...")
            await websocket.send(json.dumps({"type": "ping"}))
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Received: {data}")
            if data.get("type") != "pong":
                print(f"Error: Expected 'pong' type, got {data.get('type')}")
            else:
                print("Ping/Pong successful.")

            # 3. Test Message/Streaming
            test_message = "Hello Yuzuki! How are you today?"
            print(f"Sending message: '{test_message}'")
            await websocket.send(
                json.dumps({"type": "message", "message": test_message})
            )

            print("Waiting for streaming chunks...")
            full_response = ""
            while True:
                response = await websocket.recv()
                data = json.loads(response)

                if data.get("type") == "chunk":
                    content = data.get("content", "")
                    full_response += content
                    print(content, end="", flush=True)
                elif data.get("type") == "done":
                    print("\nStreaming complete.")
                    print(f"Final Response: {full_response.strip()}")
                    break
                elif data.get("type") == "error":
                    print(f"\nError from server: {data.get('error')}")
                    break
                else:
                    print(f"\nUnexpected message: {data}")
                    break

            print("Websocket workflow test finished successfully.")

    except Exception as e:
        print(f"Connection failed or error occurred: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run":
        asyncio.run(test_websocket())
    else:
        print("To run the test, use: python test_ws_workflow.py --run")
        print("Note: Ensure the backend server is running on localhost:8000.")
