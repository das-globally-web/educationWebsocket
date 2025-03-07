from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import mongoengine as me
from datetime import datetime
from typing import Dict
import json

# MongoDB setup with MongoEngine
me.connect('educatChatHistory', host="mongodb+srv://avbigbuddy:nZ4ATPTwJjzYnm20@cluster0.wplpkxz.mongodb.net/educatChatHistory")

# Define a ChatHistory model to store messages
class ChatHistory(me.Document):
    message = me.StringField(required=True)
    sender = me.StringField(required=True)
    recipient = me.StringField(required=True)
    timestamp = me.DateTimeField(default=datetime.utcnow)

# FastAPI app
app = FastAPI()

# Store active WebSocket connections for users (1-to-1 communication)
active_connections: Dict[str, WebSocket] = {}

# WebSocket endpoint for 1-to-1 chat
@app.websocket("/ws/chat/{user}")
async def chat(websocket: WebSocket, user: str):
    await websocket.accept()
    active_connections[user] = websocket  # ✅ Store user WebSocket connection

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)  # Expecting {"recipient": "user2", "message": "Hello"}

            recipient = message_data["recipient"]
            message = message_data["message"]

            print(f"Received message from {user} to {recipient}: {message}")

            # Store message in MongoDB chat history
            chat = ChatHistory(message=message, sender=user, recipient=recipient)
            chat.save()

            # Format message data
            formatted_message = {
                "sender": user,
                "recipient": recipient,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }

            # ✅ Send message to recipient if online
            if recipient in active_connections:
                recipient_ws = active_connections[recipient]
                await recipient_ws.send_text(json.dumps({"type": "message", "data": formatted_message}))
            else:
                # If recipient is not connected, notify sender
                await websocket.send_text(json.dumps({"type": "error", "message": f"Recipient {recipient} is not connected."}))

            # ✅ Send acknowledgment to sender
            await websocket.send_text(json.dumps({"type": "acknowledgment", "data": formatted_message}))

    except WebSocketDisconnect:
        print(f"User {user} disconnected")
        if user in active_connections:
            del active_connections[user]  # ✅ Remove user from active connections

# API endpoint to fetch old private chat messages
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
