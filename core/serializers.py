from rest_framework import serializers
from .models import *

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id','name','email','phone']
        
class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = ['id', 'address_type', 'custom_type', 'address', 'latitude', 'longitude', 'landmark', 'more_info', 'is_default', 'postal_code', 'title', 'subtitle']

class UserSerializer(serializers.ModelSerializer):
    address = UserAddressSerializer(source='useraddress', read_only=True)

    class Meta:
        model = User
        fields = ['id','email', 'phone', 'name', 'address']
        
from rest_framework import serializers
from .models import Feedback

class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ['id', 'user', 'message', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def create(self, validated_data):
        # Automatically set the user from the request context
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['user'] = request.user
        return Feedback.objects.create(**validated_data)