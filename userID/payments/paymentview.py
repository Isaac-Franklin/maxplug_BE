from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import os
from django.db.models import Q
from rest_framework import status
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.models import User
from drf_yasg.utils import swagger_auto_schema
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import login, logout, authenticate
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, schema
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.contrib.auth.hashers import make_password, check_password
from datetime import date, timedelta
from django.utils.crypto import get_random_string
from userID.models import *
from userID.payments.managetransgers import generate_transaction_key
from userID.payments.utils import generate_palmpay_signature, sign_payload
from userID.serializers import *
from firebase_admin import auth 
import uuid
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import requests
import json
import time
import hmac
import hashlib
import base64
from django.conf import settings



@swagger_auto_schema(
    method='POST',
    tags=['profile'],
)
@csrf_exempt
@api_view(['POST'])
def PalmPayTransactionNotifications(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body)
        # Log the webhook payload
        WebhookLog.objects.create(payload=payload)

        va_number = payload.get("virtual_account")
        txn_ref = payload.get("transaction_id")
        amount = payload.get("amount")
        status = payload.get("status")

        # Find the virtual account and user
        va = UserVirtualAccount.objects.get(va_number=va_number)
        user = va.user

        # Create or update transaction
        txn, created = Transaction.objects.get_or_create(
            reference=txn_ref,
            defaults={
                "user": user,
                "virtual_account": va,
                "transaction_type": "DEPOSIT",
                "amount": amount,
                "status": status,
                "idempotency_key": generate_transaction_key(),
            },
        )

        # Update transaction if it already exists
        if not created:
            txn.status = status
            txn.completed_at = timezone.now() if status == "SUCCESS" else None
            txn.save()

        # Update user's balance if successful
        if status == "SUCCESS":
            acc_balance, _ = UserAccountBalance.objects.get_or_create(
                user=user,
                virtual_account=va
            )
            acc_balance.balance += float(amount)
            acc_balance.last_updated = timezone.now()
            acc_balance.save()

        return JsonResponse({"success": True})

    except UserVirtualAccount.DoesNotExist:
        return JsonResponse({"success": False, "error": "Virtual account not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)



@swagger_auto_schema(
    method='POST',
    tags=['profile'],
)
@csrf_exempt
@api_view(['POST'])
def initiate_transfer(user, va_number, beneficiary_account_number, beneficiary_bank_code, amount):
    from django.conf import settings
    import requests

    try:
        va = UserVirtualAccount.objects.get(va_number=va_number)
        acc_balance = UserAccountBalance.objects.get(user=user, virtual_account=va)

        if acc_balance.balance < amount:
            return {"success": False, "error": "Insufficient balance"}

        # Create unique transaction reference & idempotency
        txn_ref = str(uuid.uuid4())
        idempotency_key = generate_transaction_key()

        # Record transaction as PENDING
        Transaction.objects.create(
            user=user,
            virtual_account=va,
            transaction_type="TRANSFER",
            reference=txn_ref,
            amount=amount,
            status="PENDING",
            idempotency_key=idempotency_key
        )

        # Call PalmPay transfer API
        url = f"{settings.PALMPAY_BASE_URL}/transfer"
        headers = {
            "Authorization": f"Bearer {settings.PALMPAY_API_KEY}",
            "Idempotency-Key": idempotency_key
        }
        payload = {
            "source_account": settings.MERCHANT_POOL_ACCOUNT,
            "beneficiary_account_number": beneficiary_account_number,
            "beneficiary_bank_code": beneficiary_bank_code,
            "amount": amount,
            "currency": "NGN",
            "reference": txn_ref,
            "metadata": {"user_id": user.id, "virtual_account": va_number},
            "notify_url": f"{settings.BASE_URL}/palmpay/notify"
        }

        response = requests.post(url, json=payload, headers=headers)
        data = response.json()

        return {"success": True, "data": data}

    except UserVirtualAccount.DoesNotExist:
        return {"success": False, "error": "Virtual account not found"}
    except UserAccountBalance.DoesNotExist:
        return {"success": False, "error": "Account balance not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}




# def generate_signature(data: dict, secret_key: str) -> str:
#     """
#     PalmPay signature generation:
#     1. Convert data to a sorted JSON string (without spaces)
#     2. HMAC-SHA256 hash using your secret_key
#     3. Encode result to Base64
#     """
#     # Step 1: Ensure same JSON format every time
#     payload_string = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

#     # Step 2: HMAC-SHA256 hash
#     hashed = hmac.new(
#         secret_key.encode('utf-8'),
#         payload_string.encode('utf-8'),
#         hashlib.sha256,
#     ).digest()

#     # Step 3: Convert to Base64
#     return base64.b64encode(hashed).decode('utf-8')



def generate_nonce():
    return uuid.uuid4().hex  # Random 32-character string



# @csrf_exempt
# @api_view(['POST'])
def create_virtual_account():
    payload = {
        "requestTime": int(time.time() * 1000),
        "version": "V2.0",
        "nonceStr": generate_nonce(),
        "identityType": "company",
        "customerName": "Test User",
        "virtualAccountName": "TestVA",
        "email": "user@example.com",
        "notifyUrl": "https://maxplug.xyz/palmpay/notify/"
    }

    # signature = sign_payload(payload)
    signature = generate_palmpay_signature(payload)
    print('signature')
    print(signature)

    headers = {
        "Authorization": f"Bearer L251025082741158193431",
        # "Authorization": f"Bearer {settings.PALMPAY_MERCHANT_ID}",
        "Signature": signature,
        "countryCode": "NG",
        "content-type": "application/json;charset=UTF-8"
    }

    response = requests.post(
        "https://open-gw-prod.palmpay-inc.com/api/v2/virtual/account/label/create",
        # 'https://open-gw-daily.palmpay-inc.com/api/v2/virtual/account/label/queryOne',
        data=payload,
        headers=headers
    )
    # response = requests.post(
    #     settings.PALMPAY_API_BASE_URL + "v2/virtual/account/label/create",
    #     json=payload,
    #     headers=headers
    # )
    print('response.json()')
    print(response)
    print(response.json())
    return response.json()


# runthis = create_virtual_account()
# print(runthis)


# def create_virtual_account():
#     url = "https://open-gw-daily.palmpay-inc.com/api/v2/virtual/account/label/create"

#     # ✅ Required Body
#     payload = {
#         "requestTime": int(time.time() * 1000),   # Current timestamp (ms)
#         "identityType": "company",
#         "licenseNumber": "dasd141234114123",
#         "virtualAccountName": "PPTV2",
#         "version": "V2.0",
#         "customerName": "palmpayTester",
#         "email": "2222@palmpay.com",
#         "nonceStr": "8GagBq4oGahVZAD8PQgLFJdhGQxoS1gy"  # random string
#     }

#     # ✅ Generate Signature using your secret key
#     signature = generate_signature(payload, settings.PALMPAY_SECRET_KEY)

#     # ✅ Headers
#     headers = {
#         "Authorization": f"Bearer {settings.PALMPAY_API_KEY}",  # Your merchant API Key
#         "content-type": "application/json;charset=UTF-8",
#         "countryCode": "NG",
#         "Signature": signature,
#     }

#     # ✅ Send Request
#     response = requests.post(url, json=payload, headers=headers)

#     return response.json()



















