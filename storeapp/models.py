# marketplace/models.py
# Full model file for the MaxPlug marketplace backend
# Covers: Products, Categories, Seller Profiles, Orders,
#         Wallet/Escrow, Transactions, Reviews, Notifications

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def product_image_upload_path(instance, filename):
    return f'products/{instance.product.id}/images/{filename}'

def product_video_upload_path(instance, filename):
    return f'products/{instance.product.id}/videos/{filename}'

def seller_avatar_upload_path(instance, filename):
    return f'sellers/{instance.user.id}/avatar/{filename}'

def receipt_upload_path(instance, filename):
    return f'products/{instance.product.id}/receipts/{filename}'


# ─────────────────────────────────────────────────────────────────────
# CATEGORY
# ─────────────────────────────────────────────────────────────────────

class Category(models.Model):
    """
    Top-level category (e.g. Electronics, Fashion).
    Supports one level of nesting via parent FK.
    Add more levels by chaining parent references.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=120)
    slug        = models.SlugField(max_length=140, unique=True)
    parent      = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='subcategories'
    )
    image_url   = models.URLField(blank=True, null=True)   # remote CDN image
    image       = models.ImageField(                        # or local upload
        upload_to='categories/', blank=True, null=True
    )
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        if self.parent:
            return f'{self.parent.name} → {self.name}'
        return self.name


# ─────────────────────────────────────────────────────────────────────
# SELLER PROFILE
# ─────────────────────────────────────────────────────────────────────

class SellerProfile(models.Model):
    """
    Extended profile for users who sell on the platform.
    One-to-one with Django's User model.
    """
    VERIFICATION_STATUS = [
        ('unverified',  'Unverified'),
        ('pending',     'Pending Review'),
        ('verified',    'Verified'),
        ('suspended',   'Suspended'),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user                = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_profile')
    display_name        = models.CharField(max_length=120)
    avatar              = models.ImageField(upload_to=seller_avatar_upload_path, blank=True, null=True)
    bio                 = models.TextField(blank=True, null=True)
    phone               = models.CharField(max_length=20, blank=True, null=True)
    location            = models.CharField(max_length=200, blank=True, null=True)   # e.g. "Ikeja, Lagos"
    state               = models.CharField(max_length=60, blank=True, null=True)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS, default='unverified')
    is_active           = models.BooleanField(default=True)
    commission_rate     = models.DecimalField(
        max_digits=5, decimal_places=4, default=0.0500,
        help_text='Platform commission rate, e.g. 0.0500 = 5%'
    )
    total_sales         = models.PositiveIntegerField(default=0)
    total_revenue       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rating              = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    review_count        = models.PositiveIntegerField(default=0)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Seller: {self.display_name} ({self.user.email})'


# ─────────────────────────────────────────────────────────────────────
# PRODUCT
# ─────────────────────────────────────────────────────────────────────

class Product(models.Model):
    """
    Core product listing. Supports simple and variable item types.
    Both seller-created and admin-published products use this model;
    the source field distinguishes them.
    """
    ITEM_TYPE_CHOICES = [
        ('simple',   'Simple Item'),
        ('variable', 'Variable Item'),
    ]
    CONDITION_CHOICES = [
        ('new',  'Brand New'),
        ('used', 'Used'),
        ('both', 'Both'),
    ]
    STATUS_CHOICES = [
        ('draft',      'Draft'),
        ('pending',    'Pending Review'),
        ('approved',   'Approved / Live'),
        ('rejected',   'Rejected'),
        ('suspended',  'Suspended'),
        ('sold_out',   'Sold Out'),
        ('archived',   'Archived'),
    ]
    SOURCE_CHOICES = [
        ('seller',  'Seller Listing'),
        ('admin',   'Admin Published'),
    ]
    DELIVERY_METHOD_CHOICES = [
        ('buyers_pickup',       'Buyers Pickup'),
        ('sellers_delivery',    'Sellers Delivery'),
        ('yangaplug_delivery',  'Yangaplug Delivery'),
        ('combined',            'Multiple Methods'),
    ]

    # Identifiers
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku             = models.CharField(max_length=60, unique=True, blank=True, null=True,
                                       help_text='Auto-generated or manually set SKU')

    # Ownership
    seller          = models.ForeignKey(
        SellerProfile, on_delete=models.CASCADE,
        related_name='products', null=True, blank=True,
        help_text='Null if published directly by admin'
    )
    published_by    = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        related_name='admin_published_products',
        null=True, blank=True,
        help_text='Admin user who published the product'
    )
    source          = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='seller')

    # Basic info
    name            = models.CharField(max_length=255)
    slug            = models.SlugField(max_length=280, unique=True, blank=True)
    description     = models.TextField()
    category        = models.ForeignKey(
        Category, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='products'
    )
    subcategory     = models.ForeignKey(
        Category, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sub_products',
        help_text='Optional second-level category'
    )
    tags            = models.JSONField(
        default=list, blank=True,
        help_text='List of tag strings e.g. ["hotDeal","quickDelivery"]'
    )

    # Type & condition
    item_type       = models.CharField(max_length=10, choices=ITEM_TYPE_CHOICES, default='simple')
    condition       = models.CharField(max_length=10, choices=CONDITION_CHOICES, default='new')

    # Pricing
    seller_price    = models.DecimalField(max_digits=14, decimal_places=2)
    original_price  = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        help_text='Pre-discount price shown as strikethrough'
    )
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=0.0500
    )

    @property
    def commission_amount(self):
        return self.seller_price * self.commission_rate

    @property
    def seller_earnings(self):
        return self.seller_price - self.commission_amount

    @property
    def buyer_price(self):
        """Price shown to buyer = seller_price (platform adds fees elsewhere if needed)"""
        return self.seller_price

    # Stock & delivery
    stock_count     = models.PositiveIntegerField(default=0)
    weight_kg       = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True
    )
    delivery_method = models.CharField(
        max_length=25, choices=DELIVERY_METHOD_CHOICES,
        default='sellers_delivery'
    )
    delivery_days   = models.CharField(
        max_length=20, blank=True, null=True,
        help_text='e.g. "3-5"'
    )
    dispatch_state  = models.CharField(max_length=60, blank=True, null=True)

    # Pickup address (JSON so it mirrors the Flutter model)
    pickup_address  = models.JSONField(
        null=True, blank=True,
        help_text='{"state":"...","lga":"...","street_address":"...","location_description":"..."}'
    )

    # State/LGA delivery options
    state_lga_delivery_options = models.JSONField(
        default=list, blank=True,
        help_text='List of {state, lgas, delivery_price, delivery_timeline, is_available}'
    )

    # Status & visibility
    status          = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    is_featured     = models.BooleanField(default=False)
    is_hot_deal     = models.BooleanField(default=False)
    is_quick_delivery = models.BooleanField(default=False)
    is_new_arrival  = models.BooleanField(default=False)
    admin_note      = models.TextField(
        blank=True, null=True,
        help_text='Internal note from admin (e.g. rejection reason)'
    )

    # Stats (denormalised for speed)
    view_count      = models.PositiveIntegerField(default=0)
    purchase_count  = models.PositiveIntegerField(default=0)
    rating          = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    review_count    = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    approved_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} [{self.status}]'

    def save(self, *args, **kwargs):
        # Auto-generate slug from name + short uuid if not set
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name) + '-' + str(self.id)[:8]
        super().save(*args, **kwargs)


class ProductMedia(models.Model):
    """Images and videos attached to a product."""
    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product     = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='media')
    media_type  = models.CharField(max_length=5, choices=MEDIA_TYPE_CHOICES, default='image')
    file        = models.FileField(upload_to=product_image_upload_path)
    url         = models.URLField(blank=True, null=True, help_text='Remote CDN URL if hosted externally')
    is_primary  = models.BooleanField(default=False)
    order       = models.PositiveSmallIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'{self.media_type} for {self.product.name}'

    @property
    def display_url(self):
        """Return whichever URL is available"""
        if self.url:
            return self.url
        if self.file:
            return self.file.url
        return None


class ProductReceipt(models.Model):
    """Optional receipt/proof of purchase documents for luxury items."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product     = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='receipts')
    file        = models.ImageField(upload_to=receipt_upload_path)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Receipt for {self.product.name}'


class ProductVariant(models.Model):
    """
    Used when item_type = 'variable'.
    Each variant can have its own price and stock.
    e.g. Size: L, Colour: Red, Price: ₦5000, Stock: 10
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product     = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    attributes  = models.JSONField(
        help_text='e.g. {"size": "L", "color": "Red"}'
    )
    price       = models.DecimalField(max_digits=14, decimal_places=2)
    stock       = models.PositiveIntegerField(default=0)
    sku         = models.CharField(max_length=80, blank=True, null=True)
    is_active   = models.BooleanField(default=True)

    def __str__(self):
        return f'Variant of {self.product.name}: {self.attributes}'


# ─────────────────────────────────────────────────────────────────────
# ORDER
# ─────────────────────────────────────────────────────────────────────

class Order(models.Model):
    """
    A buyer's order. One order can contain multiple OrderItems
    from the same or different sellers. Each seller sees only
    their own items via OrderItem.
    """
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('confirmed',  'Confirmed'),
        ('processing', 'Processing'),
        ('shipped',    'Shipped'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
        ('refunded',   'Refunded'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('unpaid',    'Unpaid'),
        ('paid',      'Paid'),
        ('refunded',  'Refunded'),
        ('failed',    'Failed'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number    = models.CharField(max_length=20, unique=True, blank=True)
    buyer           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='orders')
    status          = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    payment_status  = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='unpaid')

    # Delivery details
    delivery_address        = models.TextField()
    delivery_state          = models.CharField(max_length=60, blank=True, null=True)
    delivery_lga            = models.CharField(max_length=60, blank=True, null=True)
    delivery_fee            = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tracking_number         = models.CharField(max_length=100, blank=True, null=True)

    # Pricing snapshot
    subtotal        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    grand_total     = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # External reference (PHP backend transaction ID)
    external_transaction_id = models.CharField(
        max_length=100, blank=True, null=True,
        help_text='Transaction ID from the PHP/other backend wallet system'
    )

    notes           = models.TextField(blank=True, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    delivered_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order #{self.order_number}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = 'MP' + str(int(timezone.now().timestamp()))[-8:]
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    """
    A single product line within an Order.
    Stores a price snapshot so historical orders are unaffected
    by future price changes.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order           = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product         = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    seller          = models.ForeignKey(SellerProfile, on_delete=models.SET_NULL, null=True, related_name='order_items')
    variant         = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)

    # Snapshot prices at time of purchase
    product_name    = models.CharField(max_length=255)
    product_image   = models.URLField(blank=True, null=True)
    unit_price      = models.DecimalField(max_digits=14, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4)
    quantity        = models.PositiveIntegerField(default=1)

    @property
    def total(self):
        return self.unit_price * self.quantity

    @property
    def commission_amount(self):
        return self.total * self.commission_rate

    @property
    def seller_earnings(self):
        return self.total - self.commission_amount

    def __str__(self):
        return f'{self.product_name} x{self.quantity} in Order #{self.order.order_number}'


# ─────────────────────────────────────────────────────────────────────
# WALLET & ESCROW
# ─────────────────────────────────────────────────────────────────────

class SellerWallet(models.Model):
    """
    Each seller has one wallet managed entirely on this backend.
    available_balance  — funds the seller can withdraw now
    escrow_balance     — funds locked until order is confirmed delivered
    The PHP backend holds the buyer-side wallet; this backend
    only tracks seller earnings.
    """
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller              = models.OneToOneField(SellerProfile, on_delete=models.CASCADE, related_name='wallet')
    available_balance   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    escrow_balance      = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_earned        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_withdrawn     = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Synced snapshot from the PHP backend (updated periodically or on login)
    external_balance    = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Balance mirrored from the PHP/other backend wallet'
    )
    external_synced_at  = models.DateTimeField(null=True, blank=True)

    updated_at          = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Wallet: {self.seller.display_name} | Available: {self.available_balance}'


class EscrowEntry(models.Model):
    """
    Tracks funds held in escrow for a specific order item.
    Funds are released to available_balance when order is delivered.
    Funds are returned (refunded) if order is cancelled.
    """
    STATUS_CHOICES = [
        ('holding',   'Holding'),
        ('released',  'Released to Wallet'),
        ('refunded',  'Refunded to Buyer'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller          = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='escrow_entries')
    order           = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='escrow_entries')
    order_item      = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='escrow_entries')
    amount          = models.DecimalField(max_digits=14, decimal_places=2,
                                          help_text='Seller earnings held in escrow')
    status          = models.CharField(max_length=10, choices=STATUS_CHOICES, default='holding')
    held_at         = models.DateTimeField(auto_now_add=True)
    released_at     = models.DateTimeField(null=True, blank=True)
    note            = models.TextField(blank=True, null=True)

    def __str__(self):
        return f'Escrow {self.amount} for {self.seller.display_name} [{self.status}]'

    def release(self):
        """Move funds from escrow to available balance."""
        if self.status != 'holding':
            return
        wallet = self.seller.wallet
        wallet.available_balance += self.amount
        wallet.escrow_balance    -= self.amount
        wallet.save(update_fields=['available_balance', 'escrow_balance'])
        self.status      = 'released'
        self.released_at = timezone.now()
        self.save(update_fields=['status', 'released_at'])
        # Record the transaction
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='credit',
            category='escrow_release',
            amount=self.amount,
            description=f'Escrow released for Order #{self.order.order_number}',
            reference_id=str(self.order.id),
        )

    def refund(self):
        """Return funds from escrow (order cancelled/refunded)."""
        if self.status != 'holding':
            return
        wallet = self.seller.wallet
        wallet.escrow_balance -= self.amount
        wallet.save(update_fields=['escrow_balance'])
        self.status      = 'refunded'
        self.released_at = timezone.now()
        self.save(update_fields=['status', 'released_at'])
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='debit',
            category='refund',
            amount=self.amount,
            description=f'Escrow refunded for Order #{self.order.order_number}',
            reference_id=str(self.order.id),
        )


class WalletTransaction(models.Model):
    """
    Every credit or debit on a seller's wallet is recorded here.
    Provides the full transaction history for the seller dashboard.
    """
    TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit',  'Debit'),
    ]
    CATEGORY_CHOICES = [
        ('sale',            'Sale Earnings'),
        ('escrow_release',  'Escrow Release'),
        ('withdrawal',      'Withdrawal'),
        ('refund',          'Refund'),
        ('transfer',        'Transfer to Wallet'),
        ('adjustment',      'Admin Adjustment'),
        ('external_sync',   'External Balance Sync'),
    ]
    STATUS_CHOICES = [
        ('completed',   'Completed'),
        ('pending',     'Pending'),
        ('failed',      'Failed'),
        ('processing',  'Processing'),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet              = models.ForeignKey(SellerWallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type    = models.CharField(max_length=6, choices=TYPE_CHOICES)
    category            = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    amount              = models.DecimalField(max_digits=14, decimal_places=2)
    description         = models.CharField(max_length=255)
    reference_id        = models.CharField(
        max_length=100, blank=True, null=True,
        help_text='Order ID, withdrawal ID, or external reference'
    )
    status              = models.CharField(max_length=12, choices=STATUS_CHOICES, default='completed')
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.transaction_type.upper()} ₦{self.amount} — {self.description}'


class WithdrawalRequest(models.Model):
    """
    A seller's request to withdraw available balance.
    destination='bank'   → bank transfer
    destination='wallet' → transfer to the PHP-backend wallet
    """
    DESTINATION_CHOICES = [
        ('bank',   'Bank Transfer'),
        ('wallet', 'Platform Wallet'),
    ]
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
        ('cancelled',  'Cancelled'),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller              = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount              = models.DecimalField(max_digits=14, decimal_places=2)
    destination         = models.CharField(max_length=6, choices=DESTINATION_CHOICES)

    # Bank details (snapshot at time of request)
    bank_name           = models.CharField(max_length=120, blank=True, null=True)
    account_number      = models.CharField(max_length=20, blank=True, null=True)
    account_name        = models.CharField(max_length=120, blank=True, null=True)

    # Wallet transfer details
    wallet_id           = models.CharField(max_length=100, blank=True, null=True)

    status              = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    admin_note          = models.TextField(blank=True, null=True)

    # External reference from the PHP backend after transfer
    external_ref        = models.CharField(max_length=100, blank=True, null=True)

    created_at          = models.DateTimeField(auto_now_add=True)
    processed_at        = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Withdrawal ₦{self.amount} by {self.seller.display_name} [{self.status}]'


# ─────────────────────────────────────────────────────────────────────
# CART (server-side — optional, mirrors Flutter local cart)
# ─────────────────────────────────────────────────────────────────────

class Cart(models.Model):
    """
    Server-side cart for a buyer. Flutter also keeps a local copy.
    On cart open, Flutter calls GET /cart/ to sync & confirm prices.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Cart of {self.buyer.email}'


class CartItem(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart        = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product     = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    variant     = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity    = models.PositiveIntegerField(default=1)
    added_at    = models.DateTimeField(auto_now_add=True)

    @property
    def confirmed_price(self):
        """Always returns live price — never stale."""
        if self.variant:
            return self.variant.price
        if self.product:
            return self.product.seller_price
        return 0

    def __str__(self):
        name = self.product.name if self.product else 'Deleted product'
        return f'{name} x{self.quantity}'


# ─────────────────────────────────────────────────────────────────────
# REVIEW & RATING
# ─────────────────────────────────────────────────────────────────────

class ProductReview(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product     = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    buyer       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    order_item  = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True, blank=True,
                                    help_text='Ensures only verified purchasers can review')
    rating      = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment     = models.TextField(blank=True, null=True)
    is_verified = models.BooleanField(default=False, help_text='True if tied to a real purchase')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'buyer')
        ordering = ['-created_at']

    def __str__(self):
        return f'Review {self.rating}★ on {self.product.name}'


class SellerReview(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller      = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name='reviews')
    buyer       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    order       = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    rating      = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment     = models.TextField(blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('seller', 'buyer', 'order')
        ordering = ['-created_at']

    def __str__(self):
        return f'Seller review {self.rating}★ for {self.seller.display_name}'


# ─────────────────────────────────────────────────────────────────────
# CHAT (Marketplace messages)
# ─────────────────────────────────────────────────────────────────────

class Conversation(models.Model):
    """
    A conversation thread between two users (buyer↔seller or user↔admin).
    Tied to an optional product or order for context.
    """
    PARTICIPANT_TYPE_CHOICES = [
        ('buyer',  'Buyer'),
        ('seller', 'Seller'),
        ('admin',  'Admin'),
    ]

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    initiator           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='initiated_conversations')
    participant         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='received_conversations')
    participant_type    = models.CharField(max_length=6, choices=PARTICIPANT_TYPE_CHOICES, default='buyer')
    related_product     = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    related_order       = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    last_message        = models.TextField(blank=True, null=True)
    last_message_at     = models.DateTimeField(null=True, blank=True)
    unread_count        = models.PositiveIntegerField(default=0)
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_message_at']

    def __str__(self):
        return f'Conversation #{self.id} ({self.initiator} ↔ {self.participant})'


class ChatMessage(models.Model):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation    = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    text            = models.TextField()
    attachment_url  = models.URLField(blank=True, null=True)
    is_read         = models.BooleanField(default=False)
    sent_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f'Msg from {self.sender} in conv {self.conversation_id}'


# ─────────────────────────────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────────────────────────────

class Notification(models.Model):
    TYPE_CHOICES = [
        ('order_new',       'New Order'),
        ('order_update',    'Order Status Update'),
        ('payment',         'Payment'),
        ('escrow_release',  'Escrow Released'),
        ('review',          'New Review'),
        ('message',         'New Message'),
        ('system',          'System'),
        ('product_approved','Product Approved'),
        ('product_rejected','Product Rejected'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type        = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title       = models.CharField(max_length=200)
    body        = models.TextField()
    data        = models.JSONField(
        default=dict, blank=True,
        help_text='Extra payload e.g. {"order_id": "...", "product_id": "..."}'
    )
    is_read     = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.type}] {self.title} → {self.user.email}'


# ─────────────────────────────────────────────────────────────────────
# EXTERNAL BALANCE SYNC LOG
# ─────────────────────────────────────────────────────────────────────

class ExternalBalanceSyncLog(models.Model):
    """
    Records every time we sync a user's balance from the PHP backend.
    Useful for debugging and auditing the cross-system balance flow.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user            = models.ForeignKey(User, on_delete=models.CASCADE, related_name='balance_sync_logs')
    fetched_balance = models.DecimalField(max_digits=14, decimal_places=2)
    source          = models.CharField(max_length=50, default='php_backend')
    success         = models.BooleanField(default=True)
    error_message   = models.TextField(blank=True, null=True)
    synced_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-synced_at']

    def __str__(self):
        return f'Sync {self.fetched_balance} for {self.user.email} at {self.synced_at}'


