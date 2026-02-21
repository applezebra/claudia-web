import json
import os
import time
import hmac
import urllib.request
from datetime import timedelta

from http.server import BaseHTTPRequestHandler
from livekit.api import AccessToken, VideoGrants


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

        # Create room with agent dispatch via LiveKit Twirp API (sync HTTP)
        admin_token = (
            AccessToken(api_key, api_secret)
            .with_identity("serverless")
            .with_grants(VideoGrants(
                room_create=True,
                room_admin=True,
            ))
            .with_ttl(timedelta(minutes=1))
            .to_jwt()
        )

        create_body = json.dumps({
            "name": room_name,
            "empty_timeout": 60,
            "max_participants": 2,
            "agents": [
                {"agent_name": "claudia"},
            ],
        }).encode()

        # Ensure URL uses https for the API call
        api_url = livekit_url
        if api_url.startswith("wss://"):
            api_url = api_url.replace("wss://", "https://")

        req = urllib.request.Request(
            f"{api_url}/twirp/livekit.RoomService/CreateRoom",
            data=create_body,
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json",
            },
        )

        try:
            urllib.request.urlopen(req)
        except Exception as e:
            return self._json(500, {"error": f"Failed to create room: {e}"})

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

        ws_url = livekit_url
        if ws_url.startswith("https://"):
            ws_url = ws_url.replace("https://", "wss://")

        return self._json(200, {"token": token, "ws_url": ws_url})

    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
