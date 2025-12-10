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
from userID.serializers import *
from firebase_admin import auth 



@swagger_auto_schema(
    method='post',
        request_body= SignUpSerializer,
        tags=['onBoarding'],
        responses={
            200: openapi.Response(
                description="User registered",
                examples={
                    "application/json": {
                        "message": "Login successful",
                        "Token": "jwt_token",
                        "data": {"name": "name"}
                    }
                }
            ),
            400: openapi.Response(
                description="Bad request",
                examples={
                    "application/json": {
                        "error": "Email already exists"
                    }
                }
            )
        }
    )
@csrf_exempt
@api_view(['POST'])
def SaveUserData(request):
    serializer = SignUpSerializer(data = request.data)
    print('request.data')
    print(request.data)
    # check entry validation
    if serializer.is_valid():
        fullname = serializer.data['fullname']
        useremail = serializer.data['email']
        password = serializer.data['password']
        phoneNumber = serializer.data['phoneNumber']
        referrerCode = serializer.data['referrerCode']
        
        if UserDetails.objects.filter(emailAddress = useremail).exists():
            getUser = UserDetails.objects.get(emailAddress = useremail)
            fullname = getUser.fullname
            useremail = getUser.emailAddress
            phone = getUser.phoneNumber
            
            getUserusername = useremail
            getUserPassword = password
                    
            tokenCreationData = {
                'username': getUserusername,
                'password': getUserPassword
            }
            
            token_serializer = CustomTokenObtainPairSerializer(data=tokenCreationData)
            token_serializer.is_valid(raise_exception=True)
            Token = token_serializer.validated_data
                    
            # 
            
            userData = {
                "name": fullname,
                "email": useremail,
                "phone": phone,
            }
            
            return Response({
            "status": status.HTTP_200_OK,
            "message": "MaxPlug User Found.",
            "token": Token,
            "data": userData
        })
            
        else:
            saveUserData = User.objects.create_user(email = useremail, first_name = fullname, last_name = phoneNumber, password = password)
            saveUserData.save()
            
            userpassword = make_password(password)
            
            saveUser = UserDetails.objects.create(user = saveUserData, emailAddress = useremail, fullname = fullname, phoneNumber = phoneNumber, password = userpassword, referrerCode = referrerCode)
            saveUser.save()
            
            getUserusername = useremail
            getUserPassword = password
                    
            tokenCreationData = {
                'username': getUserusername,
                'password': getUserPassword
            }
            
            token_serializer = CustomTokenObtainPairSerializer(data=tokenCreationData)
            token_serializer.is_valid(raise_exception=True)
            Token = token_serializer.validated_data
            
            userData = {
                "name": fullname,
                "email": useremail,
                "phone": phoneNumber,
            }
            
            return Response({
            "status": status.HTTP_200_OK,
            "message": "MaxPlug User registered.",
            "token": Token,
            "data": userData
        })
    else:
        return Response({
            'status':status.HTTP_400_BAD_REQUEST,
            'error': 'Invalid submission data, kindly review and try again',
        })
    


@swagger_auto_schema(
    method='post',
        request_body= CheckUserAvailabilitySerializer,
        tags=['onBoarding']
    )
@csrf_exempt
@api_view(['POST'])
def CheckUserAvailability(request):
    print('CheckUserAvailability CALLED')
    serializer = CheckUserAvailabilitySerializer(data = request.data)
    # check entry validation
    if serializer.is_valid():
        fullname = serializer.data['fullname']
        useremail = serializer.data['email']
        password = serializer.data['password']
        if serializer.data['phone']:
            phone = serializer.data['phone']
        else:
            phone = ''
        
        if UserDetails.objects.filter(emailAddress = useremail).exists():
            
            userProfile = UserDetails.objects.filter(emailAddress = useremail).first()
            
            getUserusername = useremail
            getUserPassword = password
                    
            tokenCreationData = {
                'username': getUserusername,
                'password': getUserPassword
            }
            
            token_serializer = CustomTokenObtainPairSerializer(data=tokenCreationData)
            token_serializer.is_valid(raise_exception=True)
            Token = token_serializer.validated_data
            
            # create firebase mint token
            try:
                # Use the new user's PK (saveUserData.pk) as the Firebase UID
                firebase_custom_token_bytes = auth.create_custom_token(str(userProfile.pk))
                # Decode the bytes into a string, which is necessary for the JSON response
                firebase_custom_token = firebase_custom_token_bytes.decode('utf-8')
            except Exception as e:
                print(f"Error minting Firebase custom token for new user: {e}")
                firebase_custom_token = None
            
            
            userData = {
                "name": userProfile.fullname,
                "email": userProfile.emailAddress,
                "phone": userProfile.phoneNumber,
                "token": Token,
                "verificationStatus": userProfile.verificationStatus,
                "firebase_custom_token": firebase_custom_token,
            }
            
            return Response({
            "status": status.HTTP_200_OK,
            "message": "MaxPlug User registered.",
            "data": userData
            })
            
        
            
        else:
            
            saveUserData = User.objects.create_user(email = useremail, first_name = fullname, password = password, username = useremail, last_name = phone)
            saveUserData.save()
            
            saveKYCProfile =UserKYCDetails.objects.create(user = saveUserData)
            saveKYCProfile.save()
            
            userpassword = make_password(password)
            saveUser = UserDetails.objects.create(user = saveUserData, emailAddress = useremail, fullname = fullname, password = userpassword, phoneNumber = phone)
            saveUser.save()
            
            # create firebase mint token
            try:
                # Use the new user's PK (saveUserData.pk) as the Firebase UID
                firebase_custom_token_bytes = auth.create_custom_token(str(saveUserData.pk))
                # Decode the bytes into a string, which is necessary for the JSON response
                firebase_custom_token = firebase_custom_token_bytes.decode('utf-8')
            except Exception as e:
                print(f"Error minting Firebase custom token for new user: {e}")
                firebase_custom_token = None
            
            getUserusername = useremail
            getUserPassword = password
                    
            tokenCreationData = {
                'username': getUserusername,
                'password': getUserPassword
            }
            
            token_serializer = CustomTokenObtainPairSerializer(data=tokenCreationData)
            token_serializer.is_valid(raise_exception=True)
            Token = token_serializer.validated_data
            
            print('Token')
            print(Token)
            
            userData = {
                "name": fullname,
                "email": useremail,
                "verificationStatus": False,
                "firebase_custom_token": firebase_custom_token,
            }
            
            return Response({
            "status": status.HTTP_200_OK,
            "message": "MaxPlug User registered.",
            "token": Token,
            "data": userData
        })
    else:
        return Response({
            'status':status.HTTP_400_BAD_REQUEST,
            'error': 'Invalid submission data, kindly review and try again',
        })



@swagger_auto_schema(
    method='GET',
        # request_body= CheckVerificationStatus,
        tags=['onBoarding']
    )
@csrf_exempt
@api_view(['GET'])
def CheckUserVeficationStatus(request):
    if UserDetails.objects.filter(user=request.user).exists():

        try:
            kyc_details = UserKYCDetails.objects.get(user=request.user)
            
            # Use the new property for the check!
            is_kyc_complete = kyc_details.is_kyc_fully_submitted 
            
            # Parse the home address into components
            address_components = parse_home_address(kyc_details.homeaddress)
            
            # Prepare response data
            response_data = {
                "status": status.HTTP_200_OK,
                "message": "MaxPlug verification status fetched.",
                "verificationStatus": is_kyc_complete,
                "kycDetails": {
                    "level": 1,
                    # "homeaddress": kyc_details.homeaddress,
                    "dob": kyc_details.birth_date,
                    "nin": kyc_details.NIN,
                    "bvn": kyc_details.BVN,
                    # Address components broken down
                    "state": address_components.get('state', ''),
                    "city": address_components.get('city', ''),
                    "address": address_components.get('street_address', ''),
                    # 
                    
                    "idcard": kyc_details.idcard.url if kyc_details.idcard else None,
        "utilitybillimage": kyc_details.utilitybillimage.url if kyc_details.utilitybillimage else None,
                    "passportphotograph": kyc_details.passportphotograph.url if kyc_details.passportphotograph else None,
                }
            }
            
        except UserKYCDetails.DoesNotExist:
            is_kyc_complete = False
            response_data = {
                "status": status.HTTP_200_OK,
                "message": "MaxPlug verification status fetched.",
                "verificationStatus": is_kyc_complete,
                "kycDetails": {
                    "level": 1,
                    "dob": None,
                    "nin": None,
                    "bvn": None,
                    "state": None,
                    "city": None,
                    "address": None,
                }
            }

        return Response(response_data)
        
    else:
        return Response({
            'status': status.HTTP_400_BAD_REQUEST,
            'error': 'This user was not found, kindly register and try again',
        })



def parse_home_address(home_address):
    """
    Parse home address string into state, city, and street address components.
    Expected format: "Street Address, City, State"
    """
    if not home_address:
        return {
            'state': '',
            'city': '',
            'street_address': ''
        }
    
    try:
        # Split by commas and remove extra whitespace
        parts = [part.strip() for part in home_address.split(',')]
        
        # Initialize components
        state = ''
        city = ''
        street_address = ''
        
        if len(parts) >= 3:
            # Standard format: "Street Address, City, State"
            street_address = parts[0]
            city = parts[1]
            state = parts[2]
        elif len(parts) == 2:
            # If only two parts, assume "Street Address, City/State"
            street_address = parts[0]
            # Try to determine if second part is city or state
            # You might want to add more sophisticated logic here
            city_state = parts[1]
            # For now, put it in city and let the client handle it
            city = city_state
        elif len(parts) == 1:
            # If only one part, put it in street address
            street_address = parts[0]
        
        return {
            'state': state,
            'city': city,
            'street_address': street_address
        }
        
    except Exception as e:
        print(f"Error parsing home address '{home_address}': {e}")
        return {
            'state': '',
            'city': '',
            'street_address': home_address or ''
        }
        
             

@swagger_auto_schema(
    method='GET',
    tags=['profile'],
    operation_summary='Fetch authenticated user profile details',
    responses={
        200: openapi.Response(
            description="Profile fetched successfully.",
            schema=updateUserProfileSerializer,
        ),
        401: 'Unauthorized',
        404: 'Profile not found'
    }
)
@swagger_auto_schema(
    method='POST',
    request_body=updateUserProfileSerializer,
    tags=['profile'],
    operation_summary='Update authenticated user profile (name, phone, and optional image)',
    consumes=['multipart/form-data'],
    responses={
        200: 'Update successful',
        400: 'Bad Request / Validation Error',
        401: 'Unauthorized'
    }
)
@csrf_exempt
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def UpdateUserProfile(request):
    print('UpdateUserProfile CALLED by user:', request.user)
    authenticated_user = request.user

    if not authenticated_user or not authenticated_user.is_authenticated:
        return Response({
            'status': status.HTTP_401_UNAUTHORIZED,
            'error': 'Authentication required.',
        }, status=status.HTTP_401_UNAUTHORIZED)
        
    try:
        userProfile = UserDetails.objects.get(user=authenticated_user)
    except UserDetails.DoesNotExist:
        return Response({
            'status': status.HTTP_404_NOT_FOUND,
            'error': 'User profile details not found.',
        }, status=status.HTTP_404_NOT_FOUND)

    
    if request.method == 'GET':
        # --- GET: Fetching data for the authenticated user ---
        serializer = updateUserProfileSerializer(userProfile)
        
        # Get the profile image URL from the instance (not the class)
        profile_image_url = None
        if userProfile.profileImage:
            # Build the full URL using request to get the domain
            profile_image_url = request.build_absolute_uri(userProfile.profileImage.url)
        
        print('profile_image_url:', profile_image_url)
        
        return Response({
            "status": status.HTTP_200_OK,
            "message": "User details fetched.",
            "userData": {
                "name": userProfile.fullname,
                "email": userProfile.emailAddress,
                "phone": userProfile.phoneNumber,
                "verificationStatus": userProfile.verificationStatus,
                "profileImageUrl": profile_image_url,
            },
        })
        
    elif request.method == 'POST':
        # --- POST: Updating profile details ---
        print('POST data:', request.data)
        print('FILES:', request.FILES)
        
        # Use request.data for both JSON and File data
        serializer = updateUserProfileSerializer(
            userProfile, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            print('Serializer is valid. Validated data:', serializer.validated_data)
            
            updated_profile = serializer.save()
            
            # Sync fullname to User model
            if 'fullname' in serializer.validated_data:
                new_fullname = updated_profile.fullname
                authenticated_user.first_name = new_fullname
                authenticated_user.save(update_fields=['first_name'])
                print(f'Updated User.first_name to: {new_fullname}')
                
            # Sync phone to User model
            if 'phoneNumber' in serializer.validated_data:
                new_phone = updated_profile.phoneNumber
                authenticated_user.last_name = str(new_phone)
                authenticated_user.save(update_fields=['last_name'])
                print(f'Updated User.last_name to: {new_phone}')

            # Build the profile image URL (CORRECTED LOGIC)
            profile_image_url = None
            if updated_profile.profileImage: # Check the saved instance using the correct attribute name
                # Access the .url attribute of the FileField
                profile_image_url = request.build_absolute_uri(updated_profile.profileImage.url)
            
            print('Updated profile_image_url:', profile_image_url)

            return Response({
                'status': status.HTTP_200_OK,
                'message': 'User profile updated successfully and synchronized.',
                'userData': {
                    "name": updated_profile.fullname,
                    "email": updated_profile.emailAddress,
                    "phone": str(updated_profile.phoneNumber),
                    "verificationStatus": updated_profile.verificationStatus,
                    "profileImageUrl": profile_image_url,
                }
            })
        
        else:
            print('Serializer validation errors:', serializer.errors)
            return Response(
                {
                    'status': status.HTTP_400_BAD_REQUEST,
                    'error': 'Invalid submission data',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )          
         
         
            
@swagger_auto_schema(
    method='GET',
    tags=['profile'],
)
@csrf_exempt
@api_view(['GET'])
def CheckKYCDocsStatus(request):
    print('CheckKYCDocsStatus CALLED')
    try:
        kyc_details = UserKYCDetails.objects.get(user = request.user)
    except UserKYCDetails.DoesNotExist:
        return Response({
            "status": status.HTTP_200_OK,
            "message": "User KYC details not found. Please complete the KYC process.",
            "userData": {},
        }, status=status.HTTP_200_OK)

    # Use the serializer to turn the model object into a dictionary
    serializer = UserKYCDetailsSerializer(kyc_details)
    
    return Response({
        "status": status.HTTP_200_OK,
        "message": "User KYC details status fetched.",
        "userData": serializer.data,
    }, status=status.HTTP_200_OK)



@swagger_auto_schema(
    method='PATCH',
    tags=['profile'],
)
@csrf_exempt
@api_view(['PATCH'])
def UpdateKYCDocs(request):
    print("Request data:", request.data)
    
    # Ensure the user is authenticated
    if not request.user.is_authenticated:
        return Response({
            "status": status.HTTP_401_UNAUTHORIZED,
            "message": "Authentication required.",
        }, status=status.HTTP_401_UNAUTHORIZED)
        
    try:
        # Fetch the existing KYC details object for the current user
        kyc_details = UserKYCDetails.objects.get(user=request.user)
    except UserKYCDetails.DoesNotExist:
        return Response({
            "status": status.HTTP_404_NOT_FOUND,
            "message": "User KYC details not found.",
        }, status=status.HTTP_404_NOT_FOUND)

    # Create a mutable copy of request data
    # data = request.data.copy()
    data = request.data
    
    # Handle combined address data
    has_combined_address = all(key in data for key in ['state', 'city', 'address'])
    has_individual_address = 'homeaddress' in data
    
    if has_combined_address:
        # Extract address components
        state = data.get('state', '').strip()
        city = data.get('city', '').strip()
        street_address = data.get('address', '').strip()
        
        # Validate that all components are provided
        if not all([state, city, street_address]):
            return Response({
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "All address components (state, city, address) are required.",
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Concatenate into homeaddress format
        home_address = f"{street_address}, {city}, {state}"
        data['homeaddress'] = home_address
        
        # Remove individual components to avoid serializer errors
        data.pop('state', None)
        data.pop('city', None)
        data.pop('address', None)
        
        print(f"Converted address to: {home_address}")
    
    # Handle the case where both individual and combined addresses are provided
    elif has_individual_address and any(key in data for key in ['state', 'city', 'address']):
        return Response({
            "status": status.HTTP_400_BAD_REQUEST,
            "message": "Cannot provide both individual homeaddress and combined address components.",
        }, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = UserKYCDetailsSerializer(
        kyc_details, 
        data=data, 
        partial=True
    )
    
    if serializer.is_valid():
        serializer.save()
        
        # Return the updated data to the Flutter app
        return Response({
            "status": status.HTTP_200_OK,
            "message": "KYC document updated successfully.",
            "userData": serializer.data,
        }, status=status.HTTP_200_OK)
    else:
        # Return validation errors if they occur
        print("Serializer errors:", serializer.errors)
        return Response({
            "status": status.HTTP_400_BAD_REQUEST,
            "message": "Validation failed.",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='GET',
    tags=['bankDetails'],
    operation_summary='Fetch authenticated user bank account details',
    # No request_body is allowed for GET
    # responses={
    #     200: openapi.Response(
    #         description="Profile fetched successfully.",
    #         schema=updateUserProfileSerializer, # Use the serializer to define the structure
    #     ),
    #     401: 'Unauthorized',
    #     404: 'Profile not found'
    # }
)
@swagger_auto_schema(
    method='POST',
    request_body=updateUserBankAccountSerializer, # Document the fields and the file upload
    tags=['bankDetails'],
    # operation_summary='Update authenticated user profile (name, phone, and optional image)',
    # consumes=['multipart/form-data'], # Crucial for file uploads
    # responses={
    #     200: 'Update successful',
    #     400: 'Bad Request / Validation Error',
    #     401: 'Unauthorized'
    # }
)
@csrf_exempt
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ManageUserBankAccountDetails(request):
    print('ManageUserBankAccountDetails CALLED by user:', request.data)
    authenticated_user = request.user
    print(request.user)

    if not authenticated_user or not authenticated_user.is_authenticated:
        return Response({
            'status': status.HTTP_401_UNAUTHORIZED,
            'error': 'Authentication required.',
        }, status=status.HTTP_401_UNAUTHORIZED)

    
    if request.method == 'GET':
        try:
            userAccountProfile = UserAccountDetails.objects.get(user=authenticated_user)
        except UserAccountDetails.DoesNotExist:
            return Response({
                'status': status.HTTP_200_OK,
                'error': 'No bank account details saved.',
            }, status=status.HTTP_200_OK)
         
        serializer = updateUserBankAccountSerializer(userAccountProfile)
        
        
        return Response({
            "status": status.HTTP_200_OK,
            "message": "User details fetched.",
            "userAccountData": {
                "name": userAccountProfile.accountName,
                "email": userAccountProfile.bankName,
                "phone": userAccountProfile.accountNumber,
            },
        })
        
    elif request.method == 'POST':
        print('this is a post request')
        # Use request.data for both JSON and File data
        try:
            userAccountProfile = UserAccountDetails.objects.get(user=authenticated_user)
            serializer = updateUserBankAccountSerializer(userAccountProfile, data=request.data, partial=True)
        
            if serializer.is_valid():
                print('POST REQUEST IS SERIALIZED SUCCESSFULLY')
                updated_profile = serializer.save()
                
                response_serializer = updateUserBankAccountSerializer(updated_profile)
                final_data = response_serializer.data

                return Response({
                    'status': status.HTTP_200_OK,
                    'message': 'User account details updated successfully.',
                    'userData': {
                        "accountName": final_data['accountName'],
                        "bankName": final_data['bankName'],
                        "accountNumber": final_data['accountNumber'],
                        # Returns the full URL of the newly uploaded image
                    }
                })
                
        except UserAccountDetails.DoesNotExist:
            serializer = updateUserBankAccountSerializer(data=request.data)
            if serializer.is_valid():
                accountName = serializer.data['accountName']
                bankName = serializer.data['bankName']
                accountNumber = serializer.data['accountNumber']
                
                userAccountProfile = UserAccountDetails.objects.create(user = request.user, accountName = accountName, bankName = bankName, accountNumber = accountNumber), 

                return Response({
                    'status': status.HTTP_200_OK,
                    'message': 'User account details saved successfully.',
                    'userData': {
                        "accountName": accountName,
                        "bankName": bankName,
                        "accountNumber": accountNumber,
                    }
                })
        
            else:
                return Response(
                    {
                        'status': status.HTTP_400_BAD_REQUEST,
                        'error': 'Invalid submission data',
                        'errors': serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {
                    'status': status.HTTP_400_BAD_REQUEST,
                    'error': 'Invalid submission data',
                },
                status=status.HTTP_400_BAD_REQUEST
            )



@swagger_auto_schema(
    method='POST',
    request_body=FixFundingIssueSerializer,
    tags=['support'],
    operation_summary='Submit a new Fix Funding Issue'
)
@csrf_exempt
@api_view(['POST'])
def create_funding_issue(request):
    print('create_funding_issue CALLED')
    """Handles the creation of a 'Fix Funding Issue' submission."""
    print(request.data)
    # 1. Authentication Check
    if not request.user.is_authenticated:
        return Response({
            "status": status.HTTP_401_UNAUTHORIZED,
            "message": "Authentication required.",
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # 2. Validation and Save
    # We use the serializer to validate the incoming data
    serializer = FixFundingIssueSerializer(data=request.data)
    
    if serializer.is_valid():
        # Pass the current authenticated user to the save method
        submission = serializer.save(user=request.user)
        
        return Response({
            "status": status.HTTP_201_CREATED,
            "message": "Funding issue submitted successfully.",
            "submission_id": submission.id,
            "data": serializer.data,
        }, status=status.HTTP_201_CREATED)
    else:
        # 3. Return Validation Errors
        return Response({
            "status": status.HTTP_400_BAD_REQUEST,
            "message": "Validation failed.",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='POST',
    request_body=UndeliveredTransactionSerializer,
    tags=['support'],
    operation_summary='Submit a new Undelivered Transaction Issue'
)
@csrf_exempt
@api_view(['POST'])
def create_transaction_issue(request):
    """Handles the creation of an 'Undelivered Transaction' submission."""

    if not request.user.is_authenticated:
        return Response({
            "status": status.HTTP_401_UNAUTHORIZED,
            "message": "Authentication required.",
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    serializer = UndeliveredTransactionSerializer(data=request.data)
    
    if serializer.is_valid():
        submission = serializer.save(user=request.user)
        
        return Response({
            "status": status.HTTP_201_CREATED,
            "message": "Transaction issue submitted successfully.",
            "submission_id": submission.id,
            "data": serializer.data,
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            "status": status.HTTP_400_BAD_REQUEST,
            "message": "Validation failed.",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='POST',
    request_body=CardRelatedIssueSerializer,
    tags=['support'],
    operation_summary='Submit a new Card Related Issue'
)
@csrf_exempt
@api_view(['POST'])
def create_card_issue(request):
    print('create_card_issue CALLED')
    print(request.data)
    """Handles the creation of a 'Card Related Issue' submission."""

    if not request.user.is_authenticated:
        return Response({
            "status": status.HTTP_401_UNAUTHORIZED,
            "message": "Authentication required.",
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    serializer = CardRelatedIssueSerializer(data=request.data)
    
    if serializer.is_valid():
        submission = serializer.save(user=request.user)
        
        return Response({
            "status": status.HTTP_201_CREATED,
            "message": "Card issue submitted successfully.",
            "submission_id": submission.id,
            "data": serializer.data,
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            "status": status.HTTP_400_BAD_REQUEST,
            "message": "Validation failed.",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)
        


def save_faq_entry(request):
    """
    API endpoint to create a new or update an existing FAQ entry.
    Requires: question, answer, category. Optional: id (for update), order, is_active.
    """
    from .models import FAQEntry # Import locally to ensure access to model and choices
    
    try:
        data = json.loads(request.body)
        
        # 1. Validation
        required_fields = ['question', 'answer', 'category']
        if not all(field in data for field in required_fields):
            return JsonResponse({'error': 'Missing required fields (question, answer, category).'}, status=400)

        valid_categories = [c[0] for c in FAQEntry.CATEGORY_CHOICES]
        if data['category'] not in valid_categories:
            return JsonResponse({'error': f"Invalid category: {data['category']}. Must be one of {', '.join(valid_categories)}."}, status=400)
            
        faq_id = data.get('id')
        
        # 2. Retrieve or create the FAQ entry
        if faq_id:
            try:
                faq = FAQEntry.objects.get(pk=faq_id)
                created = False
            except FAQEntry.DoesNotExist:
                return JsonResponse({'error': f"FAQ with ID {faq_id} not found for update."}, status=404)
        else:
            faq = FAQEntry()
            created = True

        # 3. Update fields
        faq.question = data['question']
        faq.answer = data['answer']
        faq.category = data['category']
        faq.order = data.get('order', faq.order or 0) # Use existing or default to 0
        
        # Handle boolean field (default to True if not provided for new entries)
        if 'is_active' in data:
            faq.is_active = data['is_active']
        elif created:
            faq.is_active = True
            
        faq.save()

        status_code = 201 if created else 200
        action = 'created' if created else 'updated'
        
        return JsonResponse({
            'success': True,
            'message': f'FAQ entry successfully {action}.',
            'id': faq.id,
            'action': action
        }, status=status_code)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format.'}, status=400)
    except Exception as e:
        # Log the exception for debugging
        print(f"Error saving FAQ: {e}") 
        return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500)



# --- 3. API View Function (History Retrieval) ---

@swagger_auto_schema(
    method='GET',
    tags=['support'],
    operation_summary='Retrieve unified Selfcare History for the user',
    responses={
        200: SelfcareHistorySerializer(many=True), 
        401: 'Authentication required'
    }
)
@csrf_exempt
@api_view(['GET'])
def get_selfcare_history_details(request):
    """
    Fetches the combined history of all support submissions (Selfcare History) 
    and their admin responses for the authenticated user.
    """

    # 1. Authentication Check
    if not request.user.is_authenticated:
        return Response({
            "status": status.HTTP_401_UNAUTHORIZED,
            "message": "Authentication required.",
        }, status=status.HTTP_401_UNAUTHORIZED)

    try:
        # 2. Fetch History using the utility function from models
        history_list = get_selfcare_history(request.user)
        
        # 3. Return the combined, pre-sorted list
        return Response({
            "status": status.HTTP_200_OK,
            "message": "Selfcare history retrieved successfully.",
            "history": history_list,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        # 4. Handle unexpected errors
        print(f"Error fetching selfcare history: {e}")
        return Response({
            "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": "An unexpected error occurred while fetching history.",
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def AccountDeletionRequestView(request):
    """
    Handles submission of a new account deletion request using a Function-Based View.
    - Requires the user to be authenticated.
    - Only allows POST requests.
    """
    # Note: The @api_view(['POST']) decorator ensures this is only called for POST
    # and automatically handles request/response formatting.

    # 1. Check if an active (unprocessed) request already exists for this user.
    if AccountDeletionRequest.objects.filter(user=request.user, is_processed=False).exists():
        return Response(
            {"error": "You already have an active account deletion request pending review."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2. Validate the incoming data using the serializer
    serializer = AccountDeletionRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # 3. Save the request, linking it to the authenticated user (request.user)
    try:
        # Pass the user object explicitly to the serializer's save method
        serializer.save(user=request.user)
        return Response(
            {
                "message": "Account deletion request successfully submitted. We will process your request shortly.",
                "status_code": status.HTTP_201_CREATED,
            },
            status=status.HTTP_201_CREATED
        )
    except Exception as e:
        # General fallback for unexpected database or server errors
        print(f"Internal Server Error during deletion request: {e}")
        return Response(
            {"error": "Failed to save request due to a server issue."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



@swagger_auto_schema(
    method='POST',
    request_body=SaveFCMTokenSerializer,
    tags=['support'],
    operation_summary='Save or update user FCM token'
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def SaveFCMToken(request):
    print('SaveFCMToken CALLED')
    serializer = SaveFCMTokenSerializer(data=request.data)
    if serializer.is_valid():
        fcmtoken = serializer.validated_data.get('fcmtoken')
        user = request.user
        print('fcmtoken')
        print(fcmtoken)
        print(request.date)

        # ✅ Delete old token(s) before saving the new one
        SaveUserFCMToken.objects.filter(user=user).delete()

        # ✅ Save new token
        SaveUserFCMToken.objects.create(user=user, fcmtoken=fcmtoken)

        return Response({
            "status": status.HTTP_200_OK,
            "message": "FCM token saved successfully"
        })

    return Response({
        "status": status.HTTP_400_BAD_REQUEST,
        "errors": serializer.errors
    })

