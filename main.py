from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import mongoengine as me
from datetime import datetime
from typing import Dict
import json
import uvicorn
import httpx
import requests
import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
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

def get_access_token(credentials_path):
    """Get an OAuth 2.0 access token using a service account JSON key file."""
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    credentials.refresh(Request())
    return credentials.token

def sendNotificationss(username, message, project_id, credentials_path, device_token):
    FCM_URL = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    
    # Get the OAuth 2.0 access token
    access_token = get_access_token(credentials_path)
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "message": {
            "token": device_token,  # Device token
            "notification": {
                "title": username,
                "body": message
            },
            "android": {
                "priority": "HIGH"  # Set priority for Android devices
            },
            "apns": {
                "headers": {
                    "apns-priority": "10"  # Set priority for iOS devices
                }
            }
        }
    }
    try:
        response = requests.post(FCM_URL, headers=headers, json=payload)
        response.raise_for_status()  # Raise an error for bad status codes
        print("Notification sent successfully!")
        print("Response Status:", response.status_code)
        print("Response Body:", response.text)
        return response.json()
    except requests.exceptions.RequestException as e:
        print("Failed to send notification:", e)
        return None
project_id = "educat-5e4fa"
credentials_path = "educat-5e4fa-firebase-adminsdk-fbsvc-431f62e311.json"



@app.post("/send-notification/")
async def send_notification():
    response =  sendNotificationss(
    username="Test User",
    message="Hello! This is a test notification.",
    project_id=project_id,
    credentials_path=credentials_path)
    return {"response": response}   


# WebSocket Connection Manager
class ConnectionManager:
    """Handles WebSocket connections and messaging."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept WebSocket connection and store it."""
        await websocket.accept()

        # ✅ If user was disconnected earlier, reconnect properly
        if user_id in self.active_connections:
            print(f"🔄 User {user_id} reconnected.")
            # Close the old connection if it exists
            try:
                await self.active_connections[user_id].close()
            except Exception as e:
                print(f"❌ Error closing old connection for {user_id}: {e}")
        
        self.active_connections[user_id] = websocket
        print(f"✅ User {user_id} connected. Active users: {list(self.active_connections.keys())}")
        
        # ✅ Ensure all users get the updated active users list
        await self.notify_active_users()

    async def disconnect(self, user_id: str):
        """Remove WebSocket connection on disconnect."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"❌ User {user_id} disconnected. Updated users: {list(self.active_connections.keys())}")
        
        # ✅ Notify all users after disconnection
        await self.notify_active_users()

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
                print(f"📨 Sending message to {receiver_id}...")
                await receiver_socket.send_text(json.dumps({"type": "message", "data": formatted_message}))
                
                print(f"✅ Message sent to {receiver_id}")
            except Exception as e:
                print(f"❌ Error sending message to {receiver_id}: {e}")
                await self.disconnect(receiver_id)  # Remove inactive connection

        # ✅ Send acknowledgment to sender
        sender_socket = self.active_connections.get(sender_id)
        if sender_socket:
            try:
                print(f"✅ Sending acknowledgment to {sender_id}")
                await sender_socket.send_text(json.dumps({"type": "acknowledgment", "data": formatted_message}))
                url = f"https://education.globallywebsolutions.com/api/profile/{sender_id}"
                response = requests.get(url)
        
        # Check if the request was successful (status code 200)
                response.raise_for_status()
        
        # Parse the JSON response
                profile_data = response.json()
                print(profile_data)
                response =  sendNotificationss(
                username=f"{profile_data["data"]["email"]}",
                message=f"{message}",
                project_id=project_id,
                credentials_path=credentials_path, device_token=f"{profile_data["data"]["device_token"]}")
            except Exception as e:
                print(f"❌ Error sending acknowledgment to {sender_id}: {e}")

    async def notify_active_users(self):
        """Notify all connected users of active user list."""
        active_users_list = list(self.active_connections.keys())

        # ✅ Notify all users about the updated active users list
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps({"type": "active_users", "data": active_users_list}))
            except Exception as e:
                print(f"❌ Error notifying {user_id} of active users: {e}")
                await self.disconnect(user_id)

# Instantiate Connection Manager
manager = ConnectionManager()

@app.websocket("/ws/chat/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for user messaging."""
    await manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            print(f"🔵 Raw received data from {user_id}: {data}")  # Debugging  

            try:
                message_data = json.loads(data)
                recipient = message_data.get("recipient")
                message = message_data.get("message")

                if not recipient or not message:
                    await websocket.send_text(json.dumps({"error": "Missing recipient or message"}))
                    continue

                print(f"📩 Received message from {user_id} to {recipient}: {message}")
                await manager.send_private_message(user_id, recipient, message)

            except json.JSONDecodeError:
                print("❌ Invalid JSON format received")
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))

    except WebSocketDisconnect:
        print(f"⚠️ {user_id} disconnected")
        await manager.disconnect(user_id)

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

if __name__ == "__main__":
    uvicorn.run("main:app", port=8080, reload=True)