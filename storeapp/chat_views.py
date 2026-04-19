from django.db import transaction
from django.db.models import Q
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import Conversation, ChatMessage
from .serializers import (
    ConversationSerializer,
    ChatMessageSerializer,
    SendMessageSerializer,
    StartConversationSerializer,
)


# ─────────────────────────────────────────────────────────────────────
# GET  /chat/conversations/
# Returns all conversations for the logged-in user, newest first.
# ─────────────────────────────────────────────────────────────────────

@swagger_auto_schema(
    method='GET',
    tags=['chat'],
    operation_summary='List all conversations for the authenticated user',
    responses={
        200: openapi.Response(
            description='List of conversations',
            examples={
                'application/json': {
                    'status': 200,
                    'message': 'Conversations fetched.',
                    'data': [
                        {
                            'id': 'uuid',
                            'participant_name': 'Jane Doe',
                            'participant_avatar': None,
                            'participant_type': 'buyer',
                            'last_message': 'Is this still available?',
                            'last_message_at': '2024-01-01T10:00:00Z',
                            'unread_count': 2,
                            'related_product_name': 'iPhone 14',
                            'created_at': '2024-01-01T09:00:00Z',
                        }
                    ],
                }
            },
        ),
        401: 'Unauthorized',
    },
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conversations(request):
    """
    Returns every conversation where the authenticated user
    is either the initiator or the participant.
    """
    conversations = Conversation.objects.filter(
        Q(initiator=request.user) | Q(participant=request.user)
    ).select_related(
        'initiator', 'participant',
        'related_product', 'related_order'
    ).order_by('-last_message_at')

    serializer = ConversationSerializer(
        conversations, many=True, context={'request': request}
    )

    return Response({
        'status': status.HTTP_200_OK,
        'message': 'Conversations fetched.',
        'data': serializer.data,
    })


# ─────────────────────────────────────────────────────────────────────
# POST /chat/conversations/start/
# Find or create a conversation with another user, then send first message.
# ─────────────────────────────────────────────────────────────────────

@swagger_auto_schema(
    method='POST',
    tags=['chat'],
    operation_summary='Start a new conversation or continue an existing one',
    request_body=StartConversationSerializer,
    responses={
        200: openapi.Response(
            description='Conversation found or created, first message sent',
            examples={
                'application/json': {
                    'status': 200,
                    'message': 'Message sent.',
                    'conversation_id': 'uuid',
                    'created': False,
                    'data': {
                        'id': 'uuid',
                        'text': 'Hello!',
                        'sent_at': '2024-01-01T10:00:00Z',
                    },
                }
            },
        ),
        400: 'Validation error',
        404: 'Recipient not found',
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_conversation(request):
    """
    Find or create a 1-to-1 conversation with `recipient_id`,
    then immediately post the first message.
    Safe to call multiple times — will reuse the existing thread.
    """
    serializer = StartConversationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'status': status.HTTP_400_BAD_REQUEST,
            'message': 'Validation failed.',
            'errors': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    # Fetch recipient
    try:
        recipient = User.objects.get(pk=data['recipient_id'])
    except User.DoesNotExist:
        return Response({
            'status': status.HTTP_404_NOT_FOUND,
            'message': 'Recipient not found.',
        }, status=status.HTTP_404_NOT_FOUND)

    # Cannot message yourself
    if recipient == request.user:
        return Response({
            'status': status.HTTP_400_BAD_REQUEST,
            'message': 'You cannot message yourself.',
        }, status=status.HTTP_400_BAD_REQUEST)

    # Resolve optional FK references
    related_product = None
    related_order   = None

    if data.get('related_product_id'):
        from .models import Product
        related_product = Product.objects.filter(
            id=data['related_product_id']
        ).first()

    if data.get('related_order_id'):
        from .models import Order
        related_order = Order.objects.filter(
            id=data['related_order_id']
        ).first()

    with transaction.atomic():
        conversation, created = Conversation.get_or_create_between(
            user_a=request.user,
            user_b=recipient,
            participant_type=data.get('participant_type', 'buyer'),
            related_product=related_product,
            related_order=related_order,
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            text=data['text'],
            attachment_url=data.get('attachment_url') or None,
        )

        # Update denormalised fields on conversation
        conversation.last_message    = message.text
        conversation.last_message_at = message.sent_at
        # Increment unread for the OTHER person
        conversation.unread_count    = (
            Conversation.objects.filter(pk=conversation.pk)
            .values_list('unread_count', flat=True)
            .first() or 0
        ) + 1
        conversation.save(update_fields=[
            'last_message', 'last_message_at', 'unread_count'
        ])

    msg_serializer = ChatMessageSerializer(message, context={'request': request})

    return Response({
        'status': status.HTTP_200_OK,
        'message': 'Message sent.',
        'conversation_id': str(conversation.id),
        'created': created,
        'data': msg_serializer.data,
    })


# ─────────────────────────────────────────────────────────────────────
# GET  /chat/conversations/<conversation_id>/messages/
# Returns all messages in a conversation (marks unread as read).
# ─────────────────────────────────────────────────────────────────────

@swagger_auto_schema(
    method='GET',
    tags=['chat'],
    operation_summary='Get all messages in a conversation',
    manual_parameters=[
        openapi.Parameter(
            'conversation_id', openapi.IN_PATH,
            description='UUID of the conversation',
            type=openapi.TYPE_STRING,
        ),
    ],
    responses={
        200: openapi.Response(
            description='List of messages',
            examples={
                'application/json': {
                    'status': 200,
                    'message': 'Messages fetched.',
                    'data': [
                        {
                            'id': 'uuid',
                            'sender': {'id': 1, 'first_name': 'Jane', 'email': 'j@x.com'},
                            'sender_name': 'Jane',
                            'text': 'Hello!',
                            'attachment_url': None,
                            'is_read': True,
                            'sent_at': '2024-01-01T10:00:00Z',
                        }
                    ],
                }
            },
        ),
        403: 'Not a participant in this conversation',
        404: 'Conversation not found',
    },
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_messages(request, conversation_id):
    """
    Fetch all messages for a conversation.
    Only participants can access.
    Marks all unread messages (sent by the other party) as read
    and resets the unread_count on the conversation.
    """
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return Response({
            'status': status.HTTP_404_NOT_FOUND,
            'message': 'Conversation not found.',
        }, status=status.HTTP_404_NOT_FOUND)

    # Permission check — must be a participant
    if request.user not in (conversation.initiator, conversation.participant):
        return Response({
            'status': status.HTTP_403_FORBIDDEN,
            'message': 'You are not a participant in this conversation.',
        }, status=status.HTTP_403_FORBIDDEN)

    messages = conversation.messages.select_related('sender').all()

    # Mark unread messages from the OTHER user as read
    unread_qs = messages.filter(is_read=False).exclude(sender=request.user)
    if unread_qs.exists():
        unread_qs.update(is_read=True)
        # Reset unread counter
        conversation.unread_count = 0
        conversation.save(update_fields=['unread_count'])

    serializer = ChatMessageSerializer(
        messages, many=True, context={'request': request}
    )

    return Response({
        'status': status.HTTP_200_OK,
        'message': 'Messages fetched.',
        'data': serializer.data,
    })


# ─────────────────────────────────────────────────────────────────────
# POST /chat/conversations/<conversation_id>/messages/
# Send a message in an existing conversation.
# ─────────────────────────────────────────────────────────────────────

@swagger_auto_schema(
    method='POST',
    tags=['chat'],
    operation_summary='Send a message in an existing conversation',
    request_body=SendMessageSerializer,
    manual_parameters=[
        openapi.Parameter(
            'conversation_id', openapi.IN_PATH,
            description='UUID of the conversation',
            type=openapi.TYPE_STRING,
        ),
    ],
    responses={
        201: openapi.Response(
            description='Message sent',
            examples={
                'application/json': {
                    'status': 201,
                    'message': 'Message sent.',
                    'data': {
                        'id': 'uuid',
                        'text': 'Yes, still available!',
                        'sent_at': '2024-01-01T10:05:00Z',
                    },
                }
            },
        ),
        400: 'Validation error',
        403: 'Not a participant',
        404: 'Conversation not found',
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message(request, conversation_id):
    """
    Send a message inside an existing conversation thread.
    Only the initiator or participant can post.
    """
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return Response({
            'status': status.HTTP_404_NOT_FOUND,
            'message': 'Conversation not found.',
        }, status=status.HTTP_404_NOT_FOUND)

    if request.user not in (conversation.initiator, conversation.participant):
        return Response({
            'status': status.HTTP_403_FORBIDDEN,
            'message': 'You are not a participant in this conversation.',
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = SendMessageSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'status': status.HTTP_400_BAD_REQUEST,
            'message': 'Validation failed.',
            'errors': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        message = ChatMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            text=serializer.validated_data['text'],
            attachment_url=serializer.validated_data.get('attachment_url') or None,
        )

        conversation.last_message    = message.text
        conversation.last_message_at = message.sent_at
        # Increment unread for the OTHER person
        conversation.unread_count = (
            Conversation.objects.filter(pk=conversation.pk)
            .values_list('unread_count', flat=True)
            .first() or 0
        ) + 1
        conversation.save(update_fields=[
            'last_message', 'last_message_at', 'unread_count'
        ])

    msg_serializer = ChatMessageSerializer(message, context={'request': request})

    return Response({
        'status': status.HTTP_201_CREATED,
        'message': 'Message sent.',
        'data': msg_serializer.data,
    }, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────
# DELETE /chat/conversations/<conversation_id>/
# Soft-delete: removes the conversation + all messages for this user.
# ─────────────────────────────────────────────────────────────────────

@swagger_auto_schema(
    method='DELETE',
    tags=['chat'],
    operation_summary='Delete a conversation (for the requesting user only)',
    manual_parameters=[
        openapi.Parameter(
            'conversation_id', openapi.IN_PATH,
            description='UUID of the conversation',
            type=openapi.TYPE_STRING,
        ),
    ],
    responses={
        200: 'Conversation deleted.',
        403: 'Not a participant',
        404: 'Not found',
    },
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_conversation(request, conversation_id):
    """
    Hard-delete the conversation and all its messages.
    Only a participant can delete.
    NOTE: This deletes for BOTH participants. If you need
    per-user soft-delete, add a HiddenFor M2M field instead.
    """
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return Response({
            'status': status.HTTP_404_NOT_FOUND,
            'message': 'Conversation not found.',
        }, status=status.HTTP_404_NOT_FOUND)

    if request.user not in (conversation.initiator, conversation.participant):
        return Response({
            'status': status.HTTP_403_FORBIDDEN,
            'message': 'You are not a participant in this conversation.',
        }, status=status.HTTP_403_FORBIDDEN)

    conversation.delete()  # cascades to ChatMessage via FK

    return Response({
        'status': status.HTTP_200_OK,
        'message': 'Conversation deleted.',
    })


# ─────────────────────────────────────────────────────────────────────
# COMBINED VIEW: GET + POST /chat/conversations/<id>/messages/
# This is what urls_chat.py maps to — dispatches internally.
# ─────────────────────────────────────────────────────────────────────

@swagger_auto_schema(method='GET',  tags=['chat'], operation_summary='Get messages in a conversation')
@swagger_auto_schema(method='POST', tags=['chat'], operation_summary='Send a message in a conversation',
                     request_body=SendMessageSerializer)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def conversation_messages(request, conversation_id):
    """
    GET  → returns all messages, marks unread as read.
    POST → sends a new message.
    """
    if request.method == 'GET':
        return get_messages(request, conversation_id)
    return send_message(request, conversation_id)