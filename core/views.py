from datetime import datetime,timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import jwt
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from django.core.cache import cache
import random
from core.models import RefreshToken, User
from vroom_backend import settings
from vroom_backend.settings import EMAIL_HOST_PASSWORD,EMAIL_HOST_USER,EMAIL_HOST,EMAIL_PORT
from twilio.rest import Client
import os
from dotenv import load_dotenv
from .serializers import *
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
# Load environment variables from .env file
load_dotenv()
# Get values
account_sid = os.getenv("ACCOUNT_SID")
auth_token = os.getenv("AUTH_TOKEN")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"




def create_jwt(user_id):
    access_payload = {
        "user_id": user_id,
        "exp":datetime.utcnow() + timedelta(days=10),
        "iat": datetime.utcnow()
    }
    
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    refresh_payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=30),
        "iat": datetime.utcnow()
    }
    
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Store the refresh token in the database
    created =  RefreshToken.objects.create(user_id=user_id, token=refresh_token)

    return access_token, refresh_token

@api_view(['POST'])
def submit_feedback(request):
    
    """
    API endpoint to submit feedback.
    Expects a JSON payload with 'message' field.
    """
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return Response({"error": "Token not provided"}, status=status.HTTP_401_UNAUTHORIZED)
        if not auth_header.startswith("Bearer "):
            return Response({"error": "Invalid token format"}, status=status.HTTP_401_UNAUTHORIZED)
        
        token = auth_header.split(" ")[1]  # Extract JWT
        user_id = decode_jwt(token)  # Decode JWT
        
        if not user_id:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_401_UNAUTHORIZED)
    
        serializer = FeedbackSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Feedback submitted successfully", "data": serializer.data},
                status=status.HTTP_201_CREATED
            )
        return Response(
            {"error": "Failed to submit feedback", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        print(e)

@api_view(['GET'])
def get_user_feedback(request):
    """
    API endpoint to retrieve all feedback submitted by the authenticated user.
    """
    feedback = Feedback.objects.filter(user=request.user)
    serializer = FeedbackSerializer(feedback, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def refresh_token_view(request):
    refresh_token = request.data.get('refresh_token')

    if not refresh_token:
        return Response({"message": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get('user_id')
    except jwt.ExpiredSignatureError:
        return Response({"error": "Refresh token expired"}, status=status.HTTP_401_UNAUTHORIZED)
    except jwt.InvalidTokenError:
        return Response({"error": "Invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED)

    # Verify the refresh token exists and if exists delete -- 
    # we are checking this because what if user logs out at that point the
    # record from refresh token is deleted then an attacker tries to relogin
    # with the refresh token they can easily login if the refresh token
    # isn't expired but here we will check if it doesnt exists on db if not exists
    # that means user already logged out so it will throw an erro.=r.
    try:
        stored_token = RefreshToken.objects.get(token=refresh_token, user_id=user_id)
        stored_token.delete()
    except RefreshToken.DoesNotExist:
        return Response({"error": "Invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Issue a new access token
    access_token, new_refresh_token = create_jwt(user_id)

    return Response({
        "access_token": access_token,
        "refresh_token": new_refresh_token
    })


@api_view(['POST'])
def send_otp(request):
    data = request.data
    phone = data.get('phone')
    email = data.get('email')
    print(f'p-{phone}')
    print(f'e-{email}')

    try:
        otp = str(random.randint(100000, 999999))
        
        if phone:
            print(otp)
            cache_key = f'OTP_${phone}'
            cache.set(cache_key, otp)
            phone_setup(phone,otp)
            return Response({"message": f"{phone}"},status=status.HTTP_200_OK)
        elif email:
            print(otp)
            cache_key = f'OTP_${email}'
            cache.set(cache_key, otp)
            # email_setup(email,otp)
            print(cache)
            return Response({"message": f"{email}"},status=status.HTTP_200_OK)
        return Response({"error":"Make sure you provided a valid body [EMAIL or PHONE NUMBER]"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"Email sending failed: {e}"}, status=status.HTTP_400_BAD_REQUEST)


def phone_setup(phone, otp):
    pass
    # client = Client(account_sid, auth_token)
    # message = client.messages.create(
    #     from_ = '+15077040380',
    #     to = phone,
    #     body=f'Your otp is {otp}'
    # )
    # print(message.sid)



@api_view(['POST'])
def verify_otp(request):
    try:
        otp_from_user = request.data.get('otp')
        phone = request.data.get('phone')
        email = request.data.get('email')
       
        if phone:
            cache_key = f'OTP_${phone}'
        elif email:
            cache_key = f'OTP_${email}'
        else:
            return Response({"error": "Phone or email required"}, status=status.HTTP_400_BAD_REQUEST)

        otp_generated = cache.get(cache_key)
      
        if otp_from_user == otp_generated:
            cache.delete(cache_key) 
           
            
            user = User.objects.filter(phone=phone, email=email)
            
            if phone is not None:
                user = User.objects.filter(phone=phone)
            elif email is not None:
                user = User.objects.filter(email=email)
            
            if user.first():
                access_token, refresh_token = create_jwt(user.first().id)
                return Response({"message": "success", "user": "found","access_token":access_token,"refresh_token":refresh_token}, status=status.HTTP_200_OK)
            else:
                return Response({"message": "success", "user": "not_found"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "failed"} ,status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error':f'{e}'},status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def send_name_get_token(request):
    phone = request.data.get('phone')
    email = request.data.get('email')
    name = request.data.get('name')
    try:
        if phone:
            user = User.objects.create(phone = phone, name= name)
        elif email:
            user = User.objects.create(email = email, name= name)
        serializer = UserSerializer(user)
        access_token, refresh_token = create_jwt(user.id)
        return Response({
            "user":serializer.data,
            "message": "success",
            "access_token": access_token,
            "refresh_token": refresh_token,
        },status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error':f'{e}'},status=status.HTTP_400_BAD_REQUEST)
        
def email_setup(email, otp):
    server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
    server.starttls()  
    server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)

    msg = MIMEMultipart()
    msg["From"] = f"ABC <{EMAIL_HOST_USER}>"
    msg["To"] = email
    msg["Subject"] = "OTP Verification"
    msg.attach(MIMEText(f"Your OTP is {otp}.", "plain"))

    server.sendmail(EMAIL_HOST_USER, email, msg.as_string())
    server.quit()

    print(f"✅ Email sent to {email} with OTP: {otp}")
    

def decode_jwt(token):
    """Decodes and verifies a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except jwt.ExpiredSignatureError:
        
        return None  # Token has expired
    except jwt.InvalidTokenError:
        
        return None  # Token is invalid


@api_view(['GET'])
def test_api(request):
    print('s')
    auth_header = request.headers.get("Authorization")
    
    if not auth_header.startswith("Bearer "):
        return Response({"error": "Invalid token format"}, status=status.HTTP_401_UNAUTHORIZED)
    token = auth_header.split(" ")[1]  # Extract JWT
    user_id = decode_jwt(token)  # Decode JWT
    try:
        request.user = User.objects.get(id=user_id)
    except Exception as e:
        print(e)
    
    if not user_id:
        return Response({"error": "Invalid or expired token"}, status=status.HTTP_401_UNAUTHORIZED)

    return Response({"message": "Success", "user_id": user_id},status=status.HTTP_200_OK)


@api_view(['POST'])
def logout(request):
    refresh_token = request.data.get('refresh_token')

    if not refresh_token:
        return Response({"error": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token = RefreshToken.objects.get(token=refresh_token)
        token.delete()
        return Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
    except RefreshToken.DoesNotExist:
        return Response({"error": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def get_user_details(request):
    auth_header = request.headers.get("Authorization")
    print(auth_header)
    if not auth_header or not auth_header.startswith("Bearer "):
        return Response({"error": "Invalid token format"}, status=status.HTTP_401_UNAUTHORIZED)
    
    token = auth_header.split(" ")[1]  # Extract JWT
    user_id = decode_jwt(token)  # Decode JWT
    
    if not user_id:
        return Response({"error": "Invalid or expired token"}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        user = User.objects.get(id=user_id)
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in get_user_details: {e}")
        return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PATCH'])
def update_user_details(request):
    """
    Partially update the logged-in user's name, email, or phone.
    """
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response({"error": "Invalid token format"}, status=status.HTTP_401_UNAUTHORIZED)
        
        token = auth_header.split(" ")[1]
        user_id = decode_jwt(token)
        
        if not user_id:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserSerializer(user, data=request.data, partial=True)  # partial=True allows partial updates
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
# @permission_classes([IsAuthenticated])
def create_user_address(request):
    """
    Create a new address for the logged-in user.
    If no address with is_default=True exists, set this as default.
    """
    serializer = UserAddressSerializer(data=request.data)
    
    try:
        if serializer.is_valid():
            # Set all existing default addresses to False
            UserAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)

            # Save the new address and set it as default
            serializer.save(user=request.user, is_default=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Exception as e:
        print(e)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
# @permission_classes([IsAuthenticated])  # Uncomment later
def bulk_create_user_addresses(request):
    """
    Create multiple addresses for the logged-in user from a list.
    If no address with is_default=True exists, set the first one as default.
    """
    
    if not isinstance(request.data, list):
        return Response({"error": "Expected a list of addresses"}, status=status.HTTP_400_BAD_REQUEST)

    saved_addresses = []
    print(f'user: {request.user}')
    has_default = UserAddress.objects.filter(user=request.user, is_default=True).exists()
    try:
        for index, address_data in enumerate(request.data):
            print(f'data: {request.data}')
            serializer = UserAddressSerializer(data=address_data)
            
            if serializer.is_valid(raise_exception=True):
                # Set the first address as default if no default exists
                is_default = (index == 0) and not has_default
                serializer.save(user=request.user, is_default=is_default)
                saved_addresses.append(serializer.data)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(saved_addresses, status=status.HTTP_201_CREATED)
    except Exception as e:
        print(e)

@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def get_default_address(request):
    """
    Fetch the default address for the logged-in user.
    """
    try:
    # Fetch the default address
        default_address = UserAddress.objects.filter(user=request.user, is_default=True).first()
        
        if default_address:
            serializer = UserAddressSerializer(default_address)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        # If no default exists but addresses are present, return the first one
        first_address = UserAddress.objects.filter(user=request.user).first()
        
        if first_address:
            serializer = UserAddressSerializer(first_address)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        
        return Response({"error": "No addresses found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f'at get_default_address {e}', status=status.HTTP_404_NOT_FOUND)
        
        
@api_view(['POST'])
def make_it_default(request):
    try:
        address_id = request.data.get('id')  # Get address ID from request

        if not address_id:
            return Response({"error": "Address ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure the address belongs to the logged-in user
        if not UserAddress.objects.filter(id=address_id, user=request.user).exists():
            return Response({"error": "Invalid address or unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        # Unset the current default address for the user
        UserAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)

        # Set the selected address as default
        UserAddress.objects.filter(id=address_id, user=request.user).update(is_default=True)

        # Get the updated default address
        user_address = UserAddress.objects.get(id=address_id, user=request.user)
        serializer = UserAddressSerializer(user_address)

        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as e:
        print(e)  # Log the error
        return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def get_all_addresses(request):
    """
    Fetch all addresses for the logged-in user, regardless of default status.
    """
    try:
        addresses = UserAddress.objects.filter(user=request.user)
        if not addresses.exists():
            return Response({"message": "No addresses found"}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserAddressSerializer(addresses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f'at get_all_addresses {e}')



@api_view(['DELETE'])
# @permission_classes([IsAuthenticated])
def delete_user_address(request, id):
    try:
        print(f'request:{request}')
        address = UserAddress.objects.get(id=id, user=request.user)
        print(address)
        address.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except UserAddress.DoesNotExist:
        return Response({"error": "Address not found"}, status=status.HTTP_404_NOT_FOUND)

@api_view(['PUT'])
# @permission_classes([IsAuthenticated])
def update_user_address(request, id):
    print(f'requestUpdate:{request}')
    
    try:
        address = UserAddress.objects.get(id=id, user=request.user)
        print(address)
        serializer = UserAddressSerializer(address, data=request.data, partial=True)
        
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(e)
        return Response({"error": "Address not found"}, status=status.HTTP_404_NOT_FOUND)