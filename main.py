from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import mongoengine as me
from datetime import datetime
from typing import List, Dict
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

# Store active WebSocket connections for users
active_connections: Dict[str, WebSocket] = {}

# WebSocket endpoint to handle 1-to-1 private chat
@app.websocket("/ws/chat/{sender}/{recipient}")
async def chat(websocket: WebSocket, sender: str, recipient: str):
    # Add the WebSocket connection to the active_connections dictionary
    active_connections[sender] = websocket
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received message from {sender} to {recipient}: {data}")

            # Store message in MongoDB chat history
            chat = ChatHistory(message=data, sender=sender, recipient=recipient)
            chat.save()

            # Prepare message data in JSON format
            message_data = {
                "sender": sender,
                "recipient": recipient,
                "message": data,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Check if the recipient is connected
            if recipient in active_connections:
                recipient_ws = active_connections[recipient]
                # Send the message to the recipient in JSON format
                await recipient_ws.send_text(json.dumps({"type": "message", "data": message_data}))
            else:
                # If the recipient is not connected, notify the sender
                await websocket.send_text(json.dumps({"type": "error", "message": f"Recipient {recipient} is not connected."}))
            
            # Send the message back to the sender in JSON format
            await websocket.send_text(json.dumps({"type": "acknowledgment", "data": message_data}))

    except WebSocketDisconnect:
        print(f"User {sender} disconnected")
        del active_connections[sender]  # Remove the sender from active_connections

# API endpoint to fetch old private chat messages
@app.get("/messages/{user_name}/{other_user_name}")
async def get_old_messages(user_name: str, other_user_name: str, limit: int = 10):
    # Fetch the last 'limit' number of messages between the two users
    history = ChatHistory.objects(
        (me.Q(sender=user_name) & me.Q(recipient=other_user_name)) | 
        (me.Q(sender=other_user_name) & me.Q(recipient=user_name))
    ).order_by('-timestamp')[:limit]

    if not history:
        raise HTTPException(status_code=404, detail="No messages found")

    # Return formatted chat history
    return [
        {
            "sender": chat.sender,
            "recipient": chat.recipient,
            "message": chat.message,
            "timestamp": chat.timestamp.isoformat()
        }
        for chat in history
    ]

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", port=8080, reload=True)
