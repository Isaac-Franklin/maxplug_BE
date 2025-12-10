from django.urls import path

from userID.payments import paymentview
from . import views

urlpatterns = [
    path('savedata', views.SaveUserData, name="SaveUserData"),
    path('userlogincheck', views.CheckUserAvailability, name="CheckUserAvailability"),
    path('checkverificationstatus', views.CheckUserVeficationStatus, name="CheckUserVeficationStatus"),
    path('updateuserprofile', views.UpdateUserProfile, name="UpdateUserProfile"),
    # 
    path('checkdocs', views.CheckKYCDocsStatus, name="CheckKYCDocsStatus"),
    path('updatekycdocs', views.UpdateKYCDocs, name="UpdateKYCDocs"),
    path('updatebankaccount', views.ManageUserBankAccountDetails, name="ManageUserBankAccountDetails"),
    path('funding', views.create_funding_issue, name='create_funding_issue'),
    path('transaction', views.create_transaction_issue, name='create_transaction_issue'),
    path('card', views.create_card_issue, name='submit_card'),
    path('history', views.get_selfcare_history_details, name='history'),
    path('faqs', views.save_faq_entry, name='faqs'),
    path('deletion', views.AccountDeletionRequestView, name='account-deletion-request'),
    path('savefcmtoken', views.SaveFCMToken, name='SaveFCMToken'),
    
    # payments
    path('webhook/palmpay', paymentview.PalmPayTransactionNotifications, name='PalmPayTransactionNotifications'),
    
    
]

