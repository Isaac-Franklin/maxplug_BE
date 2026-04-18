from django.contrib import admin
from .models import *

admin.site.register(Category)
admin.site.register(SellerProfile)
admin.site.register(Product)
admin.site.register(ProductMedia)
admin.site.register(ProductReceipt)
admin.site.register(ProductVariant)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(SellerWallet)
admin.site.register(EscrowEntry)
admin.site.register(WalletTransaction)
admin.site.register(WithdrawalRequest)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(ProductReview)
admin.site.register(SellerReview)
admin.site.register(ChatMessage)
admin.site.register(Notification)
admin.site.register(ExternalBalanceSyncLog)


