# ═══════════════════════════════════════════════════════
# marketplace/signals.py
# ═══════════════════════════════════════════════════════
# Automates wallet creation, escrow management, and
# seller stats whenever related models change.

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import SellerProfile, Order, SellerWallet


@receiver(post_save, sender=SellerProfile)
def create_seller_wallet(sender, instance, created, **kwargs):
    """Auto-create a SellerWallet whenever a new SellerProfile is saved."""
    if created:
        SellerWallet.objects.get_or_create(seller=instance)


@receiver(pre_save, sender=Order)
def handle_order_status_change(sender, instance, **kwargs):
    """
    When an order transitions to 'delivered' or 'cancelled',
    trigger escrow release or refund automatically.
    """
    if not instance.pk:
        return  # new order, nothing to compare

    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    if previous.status == instance.status:
        return  # no change

    from .helpers import release_escrow_for_order, refund_escrow_for_order
    from django.utils import timezone

    if instance.status == 'delivered' and previous.status != 'delivered':
        # Release happens after save via post_save to get the updated instance,
        # but we set delivered_at here so the timestamp is correct.
        if not instance.delivered_at:
            instance.delivered_at = timezone.now()

    elif instance.status == 'cancelled' and previous.status not in ('cancelled', 'refunded'):
        # Mark for refund — actual processing in post_save below
        pass


@receiver(post_save, sender=Order)
def post_order_status_change(sender, instance, created, **kwargs):
    """Release or refund escrow after the order record is saved."""
    if created:
        return  # handled in create_order_from_items

    from .helpers import release_escrow_for_order, refund_escrow_for_order
    from .models import EscrowEntry

    holding = EscrowEntry.objects.filter(order=instance, status='holding').exists()

    if instance.status == 'delivered' and holding:
        release_escrow_for_order(instance)

    elif instance.status == 'cancelled' and holding:
        refund_escrow_for_order(instance)


# ═══════════════════════════════════════════════════════
# marketplace/apps.py
# ═══════════════════════════════════════════════════════

# from django.apps import AppConfig
#
# class MarketplaceConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'marketplace'
#
#     def ready(self):
#         import marketplace.signals  # noqa: F401


# ═══════════════════════════════════════════════════════
# marketplace/admin.py
# ═══════════════════════════════════════════════════════

from django.contrib import admin
from .models import (
    Category, SellerProfile, Product, ProductMedia, ProductReceipt,
    ProductVariant, Order, OrderItem, SellerWallet, EscrowEntry,
    WalletTransaction, WithdrawalRequest, Cart, CartItem,
    ProductReview, SellerReview, Conversation, ChatMessage,
    Notification, ExternalBalanceSyncLog,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    extra = 0
    fields = ['media_type', 'file', 'url', 'is_primary', 'order']


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ['attributes', 'price', 'stock', 'sku', 'is_active']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'seller', 'category', 'seller_price',
        'status', 'source', 'stock_count', 'is_hot_deal',
        'is_featured', 'created_at',
    ]
    list_filter = ['status', 'source', 'item_type', 'condition', 'is_hot_deal', 'is_featured']
    search_fields = ['name', 'sku', 'seller__display_name']
    readonly_fields = ['id', 'slug', 'commission_amount', 'seller_earnings', 'view_count', 'purchase_count']
    inlines = [ProductMediaInline, ProductVariantInline]
    actions = ['approve_products', 'reject_products']

    @admin.action(description='Approve selected products')
    def approve_products(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='approved', approved_at=timezone.now())

    @admin.action(description='Reject selected products')
    def reject_products(self, request, queryset):
        queryset.update(status='rejected')


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'user', 'state', 'verification_status', 'commission_rate', 'total_sales']
    list_filter = ['verification_status', 'is_active']
    search_fields = ['display_name', 'user__email', 'user__username']
    readonly_fields = ['total_sales', 'total_revenue', 'rating', 'review_count']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['total', 'commission_amount', 'seller_earnings']
    fields = ['product', 'seller', 'product_name', 'unit_price', 'quantity', 'total', 'seller_earnings']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'buyer', 'status', 'payment_status', 'grand_total', 'created_at']
    list_filter = ['status', 'payment_status']
    search_fields = ['order_number', 'buyer__email']
    readonly_fields = ['subtotal', 'grand_total']
    inlines = [OrderItemInline]


@admin.register(SellerWallet)
class SellerWalletAdmin(admin.ModelAdmin):
    list_display = ['seller', 'available_balance', 'escrow_balance', 'total_earned', 'total_withdrawn']
    search_fields = ['seller__display_name']
    readonly_fields = ['total_earned', 'total_withdrawn']


@admin.register(EscrowEntry)
class EscrowEntryAdmin(admin.ModelAdmin):
    list_display = ['seller', 'order', 'amount', 'status', 'held_at', 'released_at']
    list_filter = ['status']
    search_fields = ['seller__display_name', 'order__order_number']
    actions = ['release_escrow']

    @admin.action(description='Release selected escrow entries to wallet')
    def release_escrow(self, request, queryset):
        for entry in queryset.filter(status='holding'):
            entry.release()


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['wallet', 'transaction_type', 'category', 'amount', 'status', 'created_at']
    list_filter = ['transaction_type', 'category', 'status']
    search_fields = ['wallet__seller__display_name', 'description']
    readonly_fields = ['created_at']


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ['seller', 'amount', 'destination', 'status', 'created_at', 'processed_at']
    list_filter = ['status', 'destination']
    search_fields = ['seller__display_name', 'account_number']
    actions = ['mark_completed', 'mark_failed']

    @admin.action(description='Mark selected withdrawals as completed')
    def mark_completed(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='completed', processed_at=timezone.now())

    @admin.action(description='Mark selected withdrawals as failed')
    def mark_failed(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='failed', processed_at=timezone.now())


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'title', 'is_read', 'created_at']
    list_filter = ['type', 'is_read']
    search_fields = ['user__email', 'title']


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'buyer', 'rating', 'is_verified', 'created_at']
    list_filter = ['rating', 'is_verified']


# Simple registrations for remaining models
admin.site.register(ProductMedia)
admin.site.register(ProductReceipt)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(SellerReview)
admin.site.register(Conversation)
admin.site.register(ChatMessage)
admin.site.register(ExternalBalanceSyncLog)


