from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings

from .models import User
from .serializers import UserSerializer, CustomTokenSerializer, DoctorListSerializer


class CustomTokenView(TokenObtainPairView):
    """ Uses custom serializer to include extra user data in JWT response """
    serializer_class = CustomTokenSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    print("REQUEST DATA:", request.data)
    """ Registers a new user and returns JWT tokens with basic user info """
    serializer = UserSerializer(data=request.data, context={'request': request})

    if serializer.is_valid():
        user = serializer.save()
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            "message": "Registration successful",
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
        }, status=status.HTTP_201_CREATED)
        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth_view(request):
    token = request.data.get('id_token')
    
    if not token:
        return Response({"error": "ID Token is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        id_info = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            settings.GOOGLE_CLIENT_ID
        )

        email = id_info.get('email').lower()

        if not email.endswith('@ua.edu.ph'):
            return Response(
                {"error": "Only @ua.edu.ph email addresses are allowed."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        user = User.objects.filter(email=email).first()

        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                "action": "login",
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token)
                },
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "first_name": user.first_name,
                    "last_name": user.last_name
                }
            }, status=status.HTTP_200_OK)
        
        else:
            return Response({
                "action": "register",
                "google_info": {
                    "email": email,
                    "first_name": id_info.get('given_name', ''),
                    "last_name": id_info.get('family_name', ''),
                }
            }, status=status.HTTP_200_OK)

    except ValueError:
        return Response({"error": "Invalid Google Token"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """ Logs out the user by blacklisting the refresh token """
    try:
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        token = RefreshToken(refresh_token)
        token.blacklist() 
        
        return Response({"message": "Successfully logged out"}, status=status.HTTP_205_RESET_CONTENT)
    
    except Exception as e:
        return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_add_personnel(request):
    """ Allows admin to add new personnel """
    if request.user.role != 'admin':
        return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

    serializer = UserSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = serializer.save()
        return Response({
            "message": f"{user.role.capitalize()} created successfully",
            "user": {"username": user.username, "role": user.role}
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(viewsets.ModelViewSet):
    """ Provides CRUD operations for users (admin only) """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role != 'admin':
            # Non-admin users can only see their own profile
            return User.objects.filter(id=user.id)
        
        # Admin can see all users, with optional role filtering
        role = self.request.query_params.get('role')
        if role:
            return User.objects.filter(role=role)
        return User.objects.all()

    def perform_create(self, serializer):
        if self.request.user.role != 'admin':
            raise PermissionDenied("Only admins can create users")
        serializer.save()

    def perform_update(self, serializer):
        if self.request.user.role != 'admin':
            raise PermissionDenied("Only admins can update users")
        serializer.save()

    def perform_destroy(self, instance):
        if self.request.user.role != 'admin':
            raise PermissionDenied("Only admins can delete users")
        instance.delete()


class DoctorViewSet(viewsets.ReadOnlyModelViewSet):
    """ Provides a read-only endpoint to list all doctors """
    permission_classes = [IsAuthenticated]
    queryset = User.objects.filter(role="doctor")
    serializer_class = DoctorListSerializer 
