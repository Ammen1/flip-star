import json
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from api.models_messaging import Conversation, Message, MessageRead
from api.serializers_messaging import MessageSerializer
from django.utils import timezone


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        
        # Check if user is authenticated
        if self.scope["user"].is_anonymous:
            await self.close()
            return
        
        # Check if user is participant in conversation
        is_participant = await self.is_conversation_participant(self.conversation_id, self.scope["user"])
        if not is_participant:
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
        # Send online status
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user_id': self.scope["user"].id,
                'username': self.scope["user"].username,
            }
        )
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        
        # Send offline status
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_left',
                'user_id': self.scope["user"].id,
                'username': self.scope["user"].username,
            }
        )
    
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')
        
        if message_type == 'typing_start':
            await self.handle_typing_start()
        elif message_type == 'typing_stop':
            await self.handle_typing_stop()
        elif message_type == 'message':
            await self.handle_message(text_data_json)
        elif message_type == 'message_delivered':
            await self.handle_message_delivered(text_data_json)
        elif message_type == 'message_read':
            await self.handle_message_read(text_data_json)
    
    async def handle_typing_start(self):
        from api.services.presence_service import presence_service
        await self.set_typing_status(self.conversation_id, self.scope["user"].id, True)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user_id': self.scope["user"].id,
                'username': self.scope["user"].username,
                'is_typing': True,
            }
        )
    
    async def handle_typing_stop(self):
        from api.services.presence_service import presence_service
        await self.set_typing_status(self.conversation_id, self.scope["user"].id, False)
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user_id': self.scope["user"].id,
                'username': self.scope["user"].username,
                'is_typing': False,
            }
        )
    
    async def handle_message(self, data):
        text = data.get('text', '')
        client_uuid = data.get('uuid')
        
        # Create message
        message = await self.create_message(
            self.conversation_id,
            self.scope["user"],
            text
        )
        
        # Serialize message
        message_data = await self.serialize_message(message)
        
        # Add client UUID for optimistic UI
        message_data['client_uuid'] = client_uuid
        message_data['delivery_status'] = 'sent'
        
        # Send to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_data,
            }
        )
    
    async def handle_message_delivered(self, data):
        message_id = data.get('message_id')
        # Update message delivery status
        await self.update_message_delivery_status(message_id, 'delivered')
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'message_status_update',
                'message_id': message_id,
                'status': 'delivered',
            }
        )
    
    async def handle_message_read(self, data):
        message_id = data.get('message_id')
        # Update message read status
        await self.update_message_delivery_status(message_id, 'read')
        
        # Mark conversation as read
        await self.mark_conversation_read(self.conversation_id, self.scope["user"])
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'message_status_update',
                'message_id': message_id,
                'status': 'read',
                'user_id': self.scope["user"].id,
            }
        )
    
    async def chat_message(self, event):
        message = event['message']
        await self.send(text_data=json.dumps(message))
    
    async def typing_indicator(self, event):
        await self.send(text_data=json.dumps({
            'type': 'typing_indicator',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_typing': event['is_typing'],
        }))
    
    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'user_id': event['user_id'],
            'username': event['username'],
        }))
    
    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'user_id': event['user_id'],
            'username': event['username'],
        }))
    
    async def message_status_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_status_update',
            'message_id': event['message_id'],
            'status': event['status'],
            'user_id': event.get('user_id'),
        }))
    
    @database_sync_to_async
    def is_conversation_participant(self, conversation_id, user):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            return conversation.participants.filter(id=user.id).exists()
        except Conversation.DoesNotExist:
            return False
    
    @database_sync_to_async
    def create_message(self, conversation_id, user, text):
        conversation = Conversation.objects.get(id=conversation_id)
        message = Message.objects.create(
            conversation=conversation,
            sender=user,
            text=text,
            media_type=Message.MEDIA_TEXT,
            delivery_status=Message.DELIVERY_SENT,  # Set initial status to sent
        )
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at'])
        return message
    
    @database_sync_to_async
    def serialize_message(self, message):
        from rest_framework.request import Request
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = message.sender
        serializer = MessageSerializer(message, context={'request': request})
        return serializer.data
    
    @database_sync_to_async
    def update_message_delivery_status(self, message_id, status):
        try:
            message = Message.objects.get(id=message_id)
            if status == 'delivered':
                message.delivery_status = Message.DELIVERY_DELIVERED
                message.delivered_at = timezone.now()
            elif status == 'read':
                message.delivery_status = Message.DELIVERY_READ
                message.read_at = timezone.now()
            message.save(update_fields=['delivery_status', 'delivered_at', 'read_at'])
        except Message.DoesNotExist:
            pass
    
    @database_sync_to_async
    def mark_conversation_read(self, conversation_id, user):
        conversation = Conversation.objects.get(id=conversation_id)
        MessageRead.objects.update_or_create(
            user=user, conversation=conversation,
            defaults={'last_read_at': timezone.now()},
        )
    
    @database_sync_to_async
    def set_typing_status(self, conversation_id, user_id, is_typing):
        from api.services.presence_service import presence_service
        if is_typing:
            presence_service.set_typing(conversation_id, user_id)
        else:
            presence_service.remove_typing(conversation_id, user_id)


class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
            return
        
        self.user_group_name = f'presence_{self.scope["user"].id}'
        
        # Join user's presence group
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.accept()
        
        # Set user as online
        await self.set_user_online(self.scope["user"].id)
        
        # Notify friends that user is online
        await self.notify_friends_online_status(True)
    
    async def disconnect(self, close_code):
        # Leave user's presence group
        await self.channel_layer.group_discard(self.user_group_name, self.channel_name)
        
        # Set user as offline
        await self.set_user_offline(self.scope["user"].id)
        
        # Notify friends that user is offline
        await self.notify_friends_online_status(False)
    
    async def receive(self, text_data):
        # Handle presence updates
        pass
    
    @database_sync_to_async
    def set_user_online(self, user_id):
        from api.services.presence_service import presence_service
        presence_service.set_user_online(user_id)
    
    @database_sync_to_async
    def set_user_offline(self, user_id):
        from api.services.presence_service import presence_service
        presence_service.set_user_offline(user_id)
    
    @database_sync_to_async
    def notify_friends_online_status(self, is_online):
        """Notify friends when user goes online/offline."""
        from api.services.presence_service import presence_service
        # This would send notifications to user's friends
        # Implementation depends on how you track friendships
        pass
