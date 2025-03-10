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

# FastAPI App
app = FastAPI()

# WebSocket Connection Manager
class ConnectionManager:
    """Handles WebSocket connections and messaging."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept WebSocket connection and store it."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"User {user_id} connected. Active users: {list(self.active_connections.keys())}")

    def disconnect(self, user_id: str):
        """Remove WebSocket connection on disconnect."""
        self.active_connections.pop(user_id, None)
        print(f"User {user_id} disconnected. Updated users: {list(self.active_connections.keys())}")

    async def send_private_message(self, sender_id: str, receiver_id: str, message: str):
        """Send a message to a specific user and store in MongoDB."""
        
        # ✅ Always store message in MongoDB (Even if recipient is offline)
        chat = ChatHistory(message=message, sender=sender_id, recipient=receiver_id)
        chat.save()

        formatted_message = {
            "sender": sender_id,
            "recipient": receiver_id,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }

        # ✅ Send message if recipient is online
        receiver_socket = self.active_connections.get(receiver_id)
        if receiver_socket:
            try:
                await receiver_socket.send_text(json.dumps({"type": "message", "data": formatted_message}))
            except Exception as e:
                print(f"Error sending message to {receiver_id}: {e}")
                self.disconnect(receiver_id)  # Remove inactive connection

        # ✅ Send acknowledgment to sender
        sender_socket = self.active_connections.get(sender_id)
        if sender_socket:
            await sender_socket.send_text(json.dumps({"type": "acknowledgment", "data": formatted_message}))

# Instantiate Connection Manager
manager = ConnectionManager()

@app.websocket("/ws/chat/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for user messaging."""
    await manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Raw received data: {data}")  # Debugging

            try:
                message_data = json.loads(data)
                recipient = str(message_data.get("recipient"))
                message = message_data.get("message")
                
                if not recipient or not message:
                    await websocket.send_text(json.dumps({"error": "Missing recipient or message"}))
                    continue

                print(f"Received message from {user_id} to {recipient}: {message}")
                await manager.send_private_message(user_id, recipient, message)

            except json.JSONDecodeError:
                print("Invalid JSON format received")
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))

    except WebSocketDisconnect:
        manager.disconnect(user_id)

# API to retrieve chat history
@app.get("/messages/{user_name}/{other_user_name}")
async def get_old_messages(user_name: str, other_user_name: str, limit: int = 10):
    """Retrieve old messages between two users."""
    
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
