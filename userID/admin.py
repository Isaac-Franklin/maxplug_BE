from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(UserDetails)
admin.site.register(UserKYCDetails)
admin.site.register(UserAccountDetails)
# admin.site.register(SubmissionBase)
admin.site.register(FixFundingIssue)
admin.site.register(UndeliveredTransaction)
admin.site.register(CardRelatedIssue)
admin.site.register(FAQEntry)
admin.site.register(SaveUserFCMToken)
