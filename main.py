from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import mongoengine as me
from datetime import datetime
from typing import Dict
import json

# MongoDB setup
me.connect('educatChatHistory', host="mongodb+srv://avbigbuddy:nZ4ATPTwJjzYnm20@cluster0.wplpkxz.mongodb.net/educatChatHistory")

# ChatHistory Model
class ChatHistory(me.Document):
    message = me.StringField(required=True)
    sender = me.StringField(required=True)
    recipient = me.StringField(required=True)
    timestamp = me.DateTimeField(default=datetime.utcnow)

app = FastAPI()
active_connections: Dict[str, WebSocket] = {}

@app.websocket("/ws/chat/{user}")
async def chat(websocket: WebSocket, user: str):
    user = str(user)
    await websocket.accept()
    active_connections[user] = websocket
    print(f"User {user} connected. Active users: {list(active_connections.keys())}")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Raw received data: {data}")  # Debugging

            try:
                message_data = json.loads(data)
                recipient = str(message_data["recipient"])
                message = message_data["message"]
            except Exception as e:
                print(f"JSON parsing error: {e}")
                continue

            print(f"Received message from {user} to {recipient}: {message}")

            # Save message in MongoDB
            chat = ChatHistory(message=message, sender=user, recipient=recipient)
            chat.save()

            formatted_message = {
                "sender": user,
                "recipient": recipient,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Send to recipient if online
            if recipient in active_connections:
                recipient_ws = active_connections[recipient]
                print(f"Recipient {recipient} found in active_connections.")  # Debugging

                try:
                    await recipient_ws.send_text(json.dumps({"type": "message", "data": formatted_message}))
                except Exception as e:
                    print(f"Error sending message to {recipient}: {e}")
                    del active_connections[recipient]
            else:
                print(f"Recipient {recipient} is NOT in active_connections!")  # Debugging
                await websocket.send_text(json.dumps({"type": "error", "message": f"Recipient {recipient} is not connected."}))

            await websocket.send_text(json.dumps({"type": "acknowledgment", "data": formatted_message}))

    except WebSocketDisconnect:
        print(f"User {user} disconnected")
        if user in active_connections:
            del active_connections[user]
        print(f"Updated active users: {list(active_connections.keys())}")

@app.get("/messages/{user_name}/{other_user_name}")
async def get_old_messages(user_name: str, other_user_name: str, limit: int = 10):
    history = ChatHistory.objects(
        (me.Q(sender=user_name) & me.Q(recipient=other_user_name)) | 
        (me.Q(sender=other_user_name) & me.Q(recipient=user_name))
    ).order_by('-timestamp')[:limit]

    if not history:
        raise HTTPException(status_code=404, detail="No messages found")

    return {
        "data": [
            {
                "sender": chat.sender,
                "recipient": chat.recipient,
                "message": chat.message,
                "timestamp": chat.timestamp.isoformat()
            }
            for chat in history
        ],
        "status": True
    }

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", port=8080, reload=True)
