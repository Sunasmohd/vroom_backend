from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.

class User(models.Model):
    email = models.EmailField(unique=True, null=True,blank=True)
    phone = models.CharField(unique=True, max_length=20,null=True,blank=True)
    name = models.CharField(max_length=100, null=True,blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)
    

class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedback')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback from {self.user.username} at {self.created_at}"
    
class AddressTypeChoices(models.TextChoices):
        HOME = 'home','Home'
        WORK = 'work', 'Work'
        HOTEL = 'hotel', 'Hotel'
        PARK = 'gym', 'Gym'
        OTHER = 'other', 'Other'

class UserAddress(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    address_type = models.CharField(max_length=10,
        choices=AddressTypeChoices.choices,
        default=AddressTypeChoices.HOME,)
    custom_type = models.CharField(max_length=50,null=True,blank=True)
    address = models.TextField()
    latitude = models.CharField(max_length=30)
    longitude = models.CharField(max_length=30)
    landmark = models.CharField(max_length=100, null=True,blank=True)
    more_info = models.TextField(null=True,blank=True)
    is_default = models.BooleanField(default=False)
    postal_code = models.IntegerField(default=123)
    createdAt = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=100, default='hy')
    subtitle = models.CharField(max_length=100, default='hey')
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(address_type__in=[choice.value for choice in AddressTypeChoices]),
                name="valid_address_type"
            ),
            models.CheckConstraint(
                check=(
                    models.Q(address_type=AddressTypeChoices.OTHER, custom_type__isnull=False) & ~models.Q(custom_type="") |
                    models.Q(address_type__in=[
                        AddressTypeChoices.HOME, AddressTypeChoices.WORK, AddressTypeChoices.HOTEL,AddressTypeChoices.PARK,
                    ])
                ),
                name="valid_address_type__custom_type"
            )
        ]
    

class Profile(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    birth_date = models.DateField()
    photo_url = models.TextField()
    

class RefreshToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'RefreshToken(user={self.user}, token={self.token})'