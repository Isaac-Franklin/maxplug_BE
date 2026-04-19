# marketplace/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import *


# ─────────────────────────────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────────────────────────────

class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


# ─────────────────────────────────────────────────────────────────────
# CATEGORY
# ─────────────────────────────────────────────────────────────────────

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'image_url', 'is_active']


class CategoryTreeSerializer(serializers.ModelSerializer):
    """Nested category tree — top-level with subcategories inline."""
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'image_url', 'subcategories']

    def get_subcategories(self, obj):
        children = obj.subcategories.filter(is_active=True)
        return CategorySerializer(children, many=True).data


# ─────────────────────────────────────────────────────────────────────
# SELLER PROFILE
# ─────────────────────────────────────────────────────────────────────

class SellerProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = SellerProfile
        fields = [
            'id', 'user_id', 'user_email', 'display_name', 'avatar',
            'bio', 'phone', 'location', 'state', 'verification_status',
            'commission_rate', 'total_sales', 'total_revenue',
            'rating', 'review_count', 'is_active', 'created_at',
        ]
        read_only_fields = [
            'id', 'user_id', 'user_email', 'verification_status',
            'commission_rate', 'total_sales', 'total_revenue',
            'rating', 'review_count', 'created_at',
        ]


class SellerPublicSerializer(serializers.ModelSerializer):
    """Minimal seller info shown to buyers on product pages."""
    class Meta:
        model = SellerProfile
        fields = [
            'id', 'display_name', 'avatar', 'location',
            'rating', 'review_count', 'total_sales',
            'verification_status', 'is_active',
        ]


# ─────────────────────────────────────────────────────────────────────
# PRODUCT MEDIA
# ─────────────────────────────────────────────────────────────────────

class ProductMediaSerializer(serializers.ModelSerializer):
    display_url = serializers.ReadOnlyField()

    class Meta:
        model = ProductMedia
        fields = ['id', 'media_type', 'file', 'url', 'display_url', 'is_primary', 'order']


class ProductReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductReceipt
        fields = ['id', 'file', 'created_at']


# ─────────────────────────────────────────────────────────────────────
# PRODUCT VARIANT
# ─────────────────────────────────────────────────────────────────────

class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'attributes', 'price', 'stock', 'sku', 'is_active']


# ─────────────────────────────────────────────────────────────────────
# PRODUCT
# ─────────────────────────────────────────────────────────────────────

class ProductListSerializer(serializers.ModelSerializer):
    """Compact serializer for feed/list pages — maps to ProductModel in Flutter."""
    image_url = serializers.SerializerMethodField()
    image_urls = serializers.SerializerMethodField()
    price = serializers.DecimalField(source='seller_price', max_digits=14, decimal_places=2, coerce_to_string=False)
    original_price = serializers.DecimalField(max_digits=14, decimal_places=2, coerce_to_string=False)
    seller_id = serializers.CharField(source='seller.id', allow_null=True)
    stock_count = serializers.IntegerField(default=0)
    delivery_days = serializers.CharField()
    is_available = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    category = serializers.CharField(source='category.name', allow_null=True)
    subcategory = serializers.CharField(source='subcategory.name', allow_null=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'subcategory', 'price', 'original_price',
            'image_url', 'image_urls', 'tags', 'is_available', 'rating',
            'review_count', 'seller_id', 'stock_count', 'delivery_days',
        ]

    def get_image_url(self, obj):
        primary = obj.media.filter(is_primary=True, media_type='image').first()
        if not primary:
            primary = obj.media.filter(media_type='image').first()
        return primary.display_url if primary else None

    def get_image_urls(self, obj):
        return [m.display_url for m in obj.media.filter(media_type='image') if m.display_url]

    def get_is_available(self, obj):
        return obj.status == 'approved' and obj.stock_count > 0

    def get_tags(self, obj):
        tags = []
        if obj.is_hot_deal:
            tags.append('hotDeal')
        if obj.is_quick_delivery:
            tags.append('quickDelivery')
        if obj.is_new_arrival:
            tags.append('newArrival')
        if obj.is_featured:
            tags.append('featured')
        if obj.stock_count == 0:
            tags.append('outOfStock')
        return tags


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer — used on the product detail page."""
    image_url = serializers.SerializerMethodField()
    image_urls = serializers.SerializerMethodField()
    price = serializers.DecimalField(source='seller_price', max_digits=14, decimal_places=2, coerce_to_string=False)
    original_price = serializers.DecimalField(max_digits=14, decimal_places=2, coerce_to_string=False)
    seller_id = serializers.CharField(source='seller.id', allow_null=True)
    seller = SellerPublicSerializer(read_only=True)
    stock_count = serializers.IntegerField()
    is_available = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    attributes = serializers.SerializerMethodField()  # ← declared so get_attributes() is used
    category = serializers.CharField(source='category.name', allow_null=True)
    subcategory = serializers.CharField(source='subcategory.name', allow_null=True)
    media = ProductMediaSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    commission_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, coerce_to_string=False)
    seller_earnings = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, coerce_to_string=False)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'subcategory', 'price', 'original_price',
            'image_url', 'image_urls', 'description', 'condition', 'item_type',
            'tags', 'is_available', 'rating', 'review_count',
            'seller_id', 'seller', 'stock_count', 'delivery_days',
            'weight_kg', 'dispatch_state', 'pickup_address',
            'state_lga_delivery_options', 'delivery_method',
            'commission_rate', 'commission_amount', 'seller_earnings',
            'media', 'variants', 'attributes', 'view_count', 'purchase_count',
            'created_at', 'approved_at',
        ]

    def get_image_url(self, obj):
        primary = obj.media.filter(is_primary=True, media_type='image').first()
        if not primary:
            primary = obj.media.filter(media_type='image').first()
        return primary.display_url if primary else None

    def get_image_urls(self, obj):
        return [m.display_url for m in obj.media.filter(media_type='image') if m.display_url]

    def get_is_available(self, obj):
        return obj.status == 'approved' and obj.stock_count > 0

    def get_tags(self, obj):
        tags = []
        if obj.is_hot_deal:         tags.append('hotDeal')
        if obj.is_quick_delivery:   tags.append('quickDelivery')
        if obj.is_new_arrival:      tags.append('newArrival')
        if obj.is_featured:         tags.append('featured')
        if obj.stock_count == 0:    tags.append('outOfStock')
        return tags

    def get_attributes(self, obj):
        return obj.attributes if hasattr(obj, 'attributes') else {}


class SellerProductSerializer(serializers.ModelSerializer):
    """Seller's own view of their product — includes status, admin_note, earnings."""
    image_url = serializers.SerializerMethodField()
    price = serializers.DecimalField(source='seller_price', max_digits=14, decimal_places=2, coerce_to_string=False)
    commission_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, coerce_to_string=False)
    seller_earnings = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, coerce_to_string=False)
    category_name = serializers.CharField(source='category.name', allow_null=True)
    subcategory_name = serializers.CharField(source='subcategory.name', allow_null=True)
    media = ProductMediaSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category_name', 'subcategory_name', 'price',
            'original_price', 'image_url', 'description', 'condition',
            'item_type', 'status', 'admin_note', 'stock_count', 'weight_kg',
            'delivery_method', 'delivery_days', 'dispatch_state',
            'pickup_address', 'state_lga_delivery_options',
            'commission_rate', 'commission_amount', 'seller_earnings',
            'media', 'variants', 'view_count', 'purchase_count',
            'rating', 'review_count', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'admin_note', 'commission_rate',
            'view_count', 'purchase_count', 'rating', 'review_count',
            'created_at', 'updated_at',
        ]

    def get_image_url(self, obj):
        primary = obj.media.filter(is_primary=True, media_type='image').first()
        if not primary:
            primary = obj.media.filter(media_type='image').first()
        return primary.display_url if primary else None


class CreateProductSerializer(serializers.Serializer):
    """
    Handles POST /seller/listings/ from the Flutter app.
    Accepts the nested JSON payload + multipart media files.
    Works for both catalog-based and create-own listings.
    """
    # Step 3 — Product details
    catalog_product_id = serializers.CharField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField()
    condition = serializers.ChoiceField(choices=['new', 'used', 'both'])
    weight_kg = serializers.FloatField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=0)
    attributes = serializers.JSONField(required=False, default=dict)
    item_type = serializers.ChoiceField(choices=['simple', 'variable'], default='simple')
    category = serializers.CharField(required=False, allow_null=True)
    subcategory = serializers.CharField(required=False, allow_null=True)

    # Step 4 — Delivery
    delivery = serializers.JSONField()
    # Expected shape:
    # {
    #   "buyers_pickup": bool,
    #   "secondary_delivery": "sellers_delivery"|"yangaplug_delivery"|null,
    #   "pickup_address": {state, lga, street_address, location_description, latitude?, longitude?},
    #   "delivery_timeline": "2-3 Days",
    #   "dispatch_state": "Lagos",
    #   "state_lga_options": [{state, lgas, delivery_price, delivery_timeline, is_available}],
    #   "location_delivery_options": [{state, lgas, delivery_price, timeline, is_available}],
    # }

    # Step 5 — Pricing
    seller_price = serializers.FloatField(min_value=0)
    # Optional: if provided, overrides the auto-calculated original_price (seller_price + 20%)
    original_price = serializers.FloatField(required=False, allow_null=True, min_value=0)


# ─────────────────────────────────────────────────────────────────────
# ORDER
# ─────────────────────────────────────────────────────────────────────

class OrderItemSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, coerce_to_string=False)
    commission_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, coerce_to_string=False)
    seller_earnings = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, coerce_to_string=False)

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'seller', 'variant', 'product_name',
            'product_image', 'unit_price', 'commission_rate', 'quantity',
            'total', 'commission_amount', 'seller_earnings',
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    buyer_email = serializers.EmailField(source='buyer.email', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'buyer_email', 'status', 'payment_status',
            'delivery_address', 'delivery_state', 'delivery_lga',
            'delivery_fee', 'tracking_number', 'subtotal', 'grand_total',
            'notes', 'items', 'created_at', 'updated_at', 'delivered_at',
        ]
        read_only_fields = [
            'id', 'order_number', 'buyer_email', 'status', 'payment_status',
            'subtotal', 'grand_total', 'created_at', 'updated_at',
        ]


class CreateOrderSerializer(serializers.Serializer):
    """Payload to create an order from the cart."""
    delivery_address = serializers.CharField()
    delivery_state = serializers.CharField(required=False, allow_blank=True)
    delivery_lga = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    # List of {product_id, variant_id?, quantity}
    items = serializers.ListField(child=serializers.DictField())
    external_transaction_id = serializers.CharField(required=False, allow_blank=True)


# ─────────────────────────────────────────────────────────────────────
# WALLET & TRANSACTIONS
# ─────────────────────────────────────────────────────────────────────

class SellerWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerWallet
        fields = [
            'id', 'available_balance', 'escrow_balance',
            'total_earned', 'total_withdrawn',
            'external_balance', 'external_synced_at', 'updated_at',
        ]


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'transaction_type', 'category', 'amount',
            'description', 'reference_id', 'status', 'created_at',
        ]


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'amount', 'destination', 'bank_name', 'account_number',
            'account_name', 'wallet_id', 'status', 'admin_note',
            'external_ref', 'created_at', 'processed_at',
        ]
        read_only_fields = [
            'id', 'status', 'admin_note', 'external_ref',
            'created_at', 'processed_at',
        ]


class EscrowEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = EscrowEntry
        fields = [
            'id', 'order', 'order_item', 'amount',
            'status', 'held_at', 'released_at', 'note',
        ]


# ─────────────────────────────────────────────────────────────────────
# CART
# ─────────────────────────────────────────────────────────────────────

class CartItemSerializer(serializers.ModelSerializer):
    confirmed_price = serializers.ReadOnlyField()
    product_name = serializers.CharField(source='product.name', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'variant', 'quantity',
            'confirmed_price', 'product_name', 'image_url',
        ]

    def get_image_url(self, obj):
        if not obj.product:
            return None
        m = obj.product.media.filter(is_primary=True).first() or \
            obj.product.media.first()
        return m.display_url if m else None


class ConfirmPricesSerializer(serializers.Serializer):
    product_ids = serializers.ListField(child=serializers.CharField())


# ─────────────────────────────────────────────────────────────────────
# REVIEWS
# ─────────────────────────────────────────────────────────────────────

class ProductReviewSerializer(serializers.ModelSerializer):
    buyer_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = [
            'id', 'rating', 'comment', 'buyer_name',
            'is_verified', 'created_at',
        ]
        read_only_fields = ['id', 'buyer_name', 'is_verified', 'created_at']

    def get_buyer_name(self, obj):
        if obj.buyer:
            return obj.buyer.get_full_name() or obj.buyer.username
        return 'Anonymous'


# ─────────────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'title', 'body', 'data', 'is_read', 'created_at']
        read_only_fields = ['id', 'type', 'title', 'body', 'data', 'created_at']
        


 
class BusinessVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessVerification
        fields = [
            'id', 'status', 'admin_note',
            'business_name', 'business_state', 'business_address',
            'business_categories', 'has_ready_stock',
            'fulfillment_time', 'delivery_method', 'product_condition',
            'social_media_handle', 'submitted_at',
        ]
        read_only_fields = ['id', 'status', 'admin_note', 'submitted_at']
 
 
 
#  chat serializers
 
class SenderSerializer(serializers.ModelSerializer):
    """Minimal user info attached to each message."""
    class Meta:
        model  = User
        fields = ['id', 'first_name', 'email']
 
 
class ChatMessageSerializer(serializers.ModelSerializer):
    sender      = SenderSerializer(read_only=True)
    sender_name = serializers.SerializerMethodField()
 
    class Meta:
        model  = ChatMessage
        fields = [
            'id', 'conversation', 'sender', 'sender_name',
            'text', 'attachment_url', 'is_read', 'sent_at',
        ]
        read_only_fields = ['id', 'sender', 'sender_name', 'is_read', 'sent_at']
 
    def get_sender_name(self, obj):
        if obj.sender:
            name = obj.sender.get_full_name().strip()
            return name if name else obj.sender.email
        return 'Deleted User'
 
 
class ConversationSerializer(serializers.ModelSerializer):
    """
    Used for the conversations list screen.
    Returns enough data to render each row without an extra messages call.
    """
    participant_name   = serializers.SerializerMethodField()
    participant_avatar = serializers.SerializerMethodField()
    related_product_name = serializers.SerializerMethodField()
 
    class Meta:
        model  = Conversation
        fields = [
            'id', 'participant_name', 'participant_avatar',
            'participant_type', 'last_message', 'last_message_at',
            'unread_count', 'related_product_name', 'created_at',
        ]
 
    def get_participant_name(self, obj):
        # Return the OTHER person's name from the requesting user's perspective
        request_user = self.context.get('request').user
        other = obj.participant if obj.initiator == request_user else obj.initiator
        name = other.get_full_name().strip()
        return name if name else other.email
 
    def get_participant_avatar(self, obj):
        request_user = self.context.get('request').user
        other = obj.participant if obj.initiator == request_user else obj.initiator
        # If you have a UserDetails model with profileImage, use it:
        try:
            from userID.models import UserDetails
            profile = UserDetails.objects.get(user=other)
            if profile.profileImage:
                request = self.context.get('request')
                return request.build_absolute_uri(profile.profileImage.url)
        except Exception:
            pass
        return None
 
    def get_related_product_name(self, obj):
        return obj.related_product.name if obj.related_product else None
 
 
class SendMessageSerializer(serializers.Serializer):
    """
    Request body for POST /chat/conversations/<id>/messages/
    Only the sender and text are required; everything else is set server-side.
    """
    text           = serializers.CharField(max_length=5000)
    attachment_url = serializers.URLField(required=False, allow_blank=True)
 
 
class StartConversationSerializer(serializers.Serializer):
    """
    Request body for POST /chat/conversations/start/
    Finds or creates a conversation thread then sends the first message.
    """
    recipient_id      = serializers.IntegerField(
        help_text='Django User.id of the person you want to message'
    )
    text              = serializers.CharField(max_length=5000)
    attachment_url    = serializers.URLField(required=False, allow_blank=True)
    participant_type  = serializers.ChoiceField(
        choices=['buyer', 'seller', 'admin'], default='buyer'
    )
    related_product_id = serializers.UUIDField(required=False, allow_null=True)
    related_order_id   = serializers.UUIDField(required=False, allow_null=True)
