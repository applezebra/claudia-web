import json
import os
import time
import hmac
from datetime import timedelta

from http.server import BaseHTTPRequestHandler
from livekit.api import LiveKitAPI, CreateRoomRequest, RoomAgentDispatch
from livekit.api.access_token import AccessToken, VideoGrants


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            return self._json(400, {"error": "Invalid request body"})

        pin = body.get("pin", "")
        expected = os.environ.get("CLAUDIA_PIN", "")

        if not expected or not hmac.compare_digest(str(pin), expected):
            return self._json(403, {"error": "Wrong PIN"})

        api_key = os.environ["LIVEKIT_API_KEY"]
        api_secret = os.environ["LIVEKIT_API_SECRET"]
        livekit_url = os.environ["LIVEKIT_URL"]

        room_name = f"claudia-{int(time.time())}"

        # Create room with agent dispatch
        import asyncio

        async def setup():
            lk = LiveKitAPI(livekit_url, api_key, api_secret)
            try:
                await lk.room.create_room(
                    CreateRoomRequest(
                        name=room_name,
                        empty_timeout=60,
                        max_participants=2,
                        agent=RoomAgentDispatch(
                            agent_name="claudia",
                        ),
                    )
                )
            finally:
                await lk.aclose()

        asyncio.run(setup())

        # Generate participant token
        token = (
            AccessToken(api_key, api_secret)
            .with_identity("anson")
            .with_name("Anson")
            .with_grants(VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))
            .with_ttl(timedelta(hours=1))
            .to_jwt()
        )

        ws_url = livekit_url.replace("https://", "wss://").replace("http://", "ws://")

        return self._json(200, {"token": token, "ws_url": ws_url})

    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
