from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from appointments.utils import encrypt, decrypt
from .models import User  


class CustomTokenSerializer(TokenObtainPairSerializer):
    """ Adds user role and details to the token """

    # Include role and user details in the token response
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        return token

    # Include user details in the token response
    def validate(self, attrs):
        data =super().validate(attrs)
        data['role'] = self.user.role  
        data['first_name'] = self.user.first_name
        data['last_name'] = self.user.last_name
        return data
    

class UserSerializer(serializers.ModelSerializer):
    """ Handles user registration, validation, and role assignment """

    # Defines required user fields for input
    username = serializers.CharField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        # Connects to the User model and specifies fields to include
        model = User
        fields = [
                'id', 'username', 'first_name', 'last_name', 'email', 
                'password', 'role', 'date_of_birth', 'sex', 'contact_number', 
                'address', 'course', 'year', 'section',
            ]

    def validate(self, data):
        # Check if Patient has provided Academic Info
        role = data.get('role', 'patient')
        errors = {}

        if role == 'patient':
            patient_required_fields = [
                'course', 'year', 'section', 'date_of_birth', 
                'sex', 'contact_number', 'address'
            ]
            
            for field in patient_required_fields:
                if not data.get(field):
                    errors[field] = "This field is required for students."
        
        if errors:
            raise serializers.ValidationError(errors)
                
        return data

    def validate_username(self, value):
        # Checks if username already exists
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value
    
    def validate_email(self, value):
        # Checks if email already exists
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        requested_role = validated_data.get('role')

        is_admin = (request and 
                    request.user.is_authenticated and 
                    getattr(request.user, 'role', None) == 'admin')

        if is_admin and requested_role in ['doctor', 'admin']:
            role = requested_role
        else:
            role = 'patient'

        # ENCRYPT FIELDS
        sensitive_fields = [
            'address', 'contact_number',
        ]

        for field in sensitive_fields:
            if validated_data.get(field):
                validated_data[field] = encrypt(validated_data[field])

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            role=role,

            date_of_birth=validated_data.get('date_of_birth'),
            sex=validated_data.get('sex'),
            contact_number=validated_data.get('contact_number'),
            address=validated_data.get('address'),
            course=validated_data.get('course'),
            year=validated_data.get('year'),
            section=validated_data.get('section'),
        )

        return user
    
    def to_representation(self, instance):
        ret = super().to_representation(instance)

        # DECRYPT FIELDS
        decrypt_fields = [
            'address', 'contact_number',
        ]

        for field in decrypt_fields:
            try:
                if ret.get(field):
                    ret[field] = decrypt(ret[field])
            except Exception:
                ret[field] = "[Decryption Error]"

        return ret


class DoctorListSerializer(serializers.ModelSerializer):
    """ List serializer for doctors with full name and role """
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'full_name', 'role', 'specialization']

    def get_full_name(self, obj):
        spec = (obj.specialization or "").lower()
        role = (obj.role or "").lower()

        if "dentist" in spec:
            prefix = "Dentist"
        elif "nurse" in spec or role == "nurse":
            prefix = "Nurse"
        elif role == "doctor":
            prefix = "Dr."
        else:
            prefix = ""

        first = obj.first_name.title()
        last = obj.last_name.title()

        return f"{prefix} {first} {last}".strip()