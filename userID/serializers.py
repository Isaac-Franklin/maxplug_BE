from enum import Enum
from typing import OrderedDict
from rest_framework import serializers
from .models import *
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import serializers



class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['username'] = user.username
        token['email'] = user.email

        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer



class SignUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDetails
        fields = ['fullname', 'emailAddress', 'phoneNumber', 'referrerCode', 'password']






class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class CheckUserAvailabilitySerializer(serializers.Serializer):
    email = serializers.EmailField()
    fullname = serializers.CharField()
    password = serializers.CharField()
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    

class CheckVerificationStatus(serializers.Serializer):
    email = serializers.EmailField()


class UserEmailAddressSerialzier(serializers.Serializer):
    email = serializers.EmailField()


class UpdateVerificationStatus(serializers.ModelSerializer):
    class Meta:
        model = UserDetails
        fields = ['verificationStatus']


class updateUserProfileSerializer(serializers.ModelSerializer):
    # This field is for output only (read-only)
    emailAddress = serializers.EmailField(read_only=True) 
    
    # FIX: Explicitly define the field to handle the snake_case input ('profile_image')
    # and map it to the camelCase model field ('profileImage').
    profile_image = serializers.ImageField(
        source='profileImage',  # <-- CRITICAL: Maps incoming 'profile_image' to model's 'profileImage'
        required=False,
        allow_null=True,        # Allow field to be explicitly null if sent
        write_only=True         # Good practice for upload fields
    )

    class Meta:
        model = UserDetails
        # Include the new, explicitly defined field name ('profile_image') 
        # instead of the model field name ('profileImage').
        fields = ('fullname', 'phoneNumber', 'profile_image', 'emailAddress') 
        
        extra_kwargs = {
            'fullname': {'required': False},
            'phoneNumber': {'required': False},
            # We don't need 'profileImage' here anymore as 'profile_image' handles it.
        }

    def update(self, instance, validated_data):
        # NOTE: Due to the `source='profileImage'` argument above, the key 
        # in `validated_data` will now be 'profileImage', matching the model attribute name.
        
        print('Serializer Update - Validated Data (POST-FIX):', validated_data)
        
        # 1. Update fields if they exist in the incoming data
        instance.fullname = validated_data.get('fullname', instance.fullname)
        instance.phoneNumber = validated_data.get('phoneNumber', instance.phoneNumber)
        
        # 2. Handle ImageField update (key is 'profileImage' now)
        if 'profileImage' in validated_data:
            instance.profileImage = validated_data['profileImage']

        # 3. Save the instance to the database
        instance.save()
        print('Profile saved successfully.')

        # 4. Return the updated instance
        return instance
    
    
class UserKYCDetailsSerializer(serializers.ModelSerializer):
    # Custom field names for the URLs
    idcard = serializers.ImageField()
    utilitybillimage = serializers.ImageField()
    passportphotograph = serializers.ImageField()
    
    class Meta:
        model = UserKYCDetails
        fields = (
            'homeaddress', 
            'NIN', 
            'birth_date',
            'BVN', 
            'idcard', 
            'utilitybillimage',
            'passportphotograph',
        )

    # Method to get the URL for the ID Card
    def get_idcard(self, obj):
        # Check if the image field has a file attached
        if obj.idcard:
            return obj.idcard.url
        return None

    # Method to get the URL for the Utility Bill
    def get_utilitybillimage(self, obj):
        if obj.utilitybillimage:
            return obj.utilitybillimage.url
        return None



class updateUserBankAccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = UserAccountDetails
        # Define the fields the user is allowed to send for update/read.
        fields = ('accountName', 'bankName', 'accountNumber') 
        # Make everything writable except email, and allow partial updates
        extra_kwargs = {
            'accountName': {'required': False},
            'bankName': {'required': False},
            'accountNumber': {'required': False},
        }

    # CRITICAL FIX: The update method required by serializer.save()
    def update(self, instance, validated_data):
        """
        Updates the UserDetails instance with the validated data.
        This handles all database updates for the UserDetails model fields.
        """ 
        print('validated_data')
        print(validated_data)
        print('instance')
        print(instance)
        
        # 1. Update fields if they exist in the incoming data
        instance.accountName = validated_data.get('accountName', instance.accountName)
        instance.bankName = validated_data.get('bankName', instance.bankName)
        instance.accountNumber = validated_data.get('accountNumber', instance.accountNumber)
        
        
        instance.save()

        return instance




class FixFundingIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = FixFundingIssue
        fields = [
            'deposit_amount', 
            'reference_id', 
            'proof_of_payment', 
            'issue_description'
        ]

class UndeliveredTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UndeliveredTransaction
        fields = [
            'transaction_type', 
            'recipient_details', 
            'transaction_id', 
            'amount'
        ]

class CardRelatedIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = CardRelatedIssue
        fields = [
            'issue_category', 
            'card_reference', 
            'issue_description'
        ]

class SelfcareHistorySerializer(serializers.Serializer):
    """
    Serializer to define the structure of the unified history list for Swagger.
    Note: This is just for documentation and output formatting.
    """
    issue_type = serializers.CharField(max_length=50)
    summary = serializers.CharField(max_length=255)
    issue_description = serializers.CharField()
    status = serializers.CharField(max_length=20)
    admin_response = serializers.CharField(required=False, allow_null=True)
    created_at = serializers.DateTimeField()



class AccountDeletionRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for validating and creating AccountDeletionRequest objects.
    """
    class Meta:
        model = AccountDeletionRequest
        # We only expect reason and feedback from the client
        fields = ['primary_reason', 'detailed_feedback']
        read_only_fields = ['requested_at']




class SaveFCMTokenSerializer(serializers.Serializer):
    fcmtoken = serializers.CharField(max_length=70)



    
    