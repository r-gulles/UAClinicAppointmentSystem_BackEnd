from django.utils import timezone
from rest_framework import viewsets
from .models import Appointment
from .serializers import AppointmentSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.decorators import action
from datetime import timedelta
from django.db.models import Q


class AppointmentViewSet(viewsets.ModelViewSet):
    """ Handles CRUD operations for appointments with role-based access control and validation """
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Returns appointments based on user role and filters
        user = self.request.user
        doctor_id = self.request.query_params.get('doctor')
        date_str = self.request.query_params.get('date')

        # Auto-update statuses for past appointments
        now_local = timezone.localtime(timezone.now())
        grace_cutoff = now_local - timedelta(hours=1)

        # AUTO-COMPLETE (Only if older than 1 hour)
        Appointment.objects.filter(
            status="Approved", 
            date_time__lt=grace_cutoff
        ).update(status="Completed")

        # AUTO-EXPIRE (Only if Pending and time has passed)
        Appointment.objects.filter(
            status="Pending", 
            date_time__lt=now_local
        ).update(status="Expired")

        search_query = self.request.query_params.get('search')

        # Returns doctor availability view
        if doctor_id and date_str:
            return Appointment.objects.filter(
                doctor_id=doctor_id, 
                date_time__date=date_str
            ).order_by('-date_time')

        # Returns user-specific dashboard data 
        if user.role == 'admin':
            queryset = Appointment.objects.all()
        elif user.role == 'doctor':
            queryset = Appointment.objects.filter(doctor=user)
        else:
            queryset = Appointment.objects.filter(patient=user)

        # 
        if date_str:
            queryset = queryset.filter(date_time__date=date_str)

        if search_query:
            terms = search_query.strip().split()

            query = Q()
            for term in terms:
                query &= (
                    Q(patient__first_name__icontains=term) |
                    Q(patient__last_name__icontains=term)
                )

            queryset = queryset.filter(query)

        return queryset.order_by('-date_time')
    

    def perform_create(self, serializer):
        # Automatically assigns logged-in user as patient
        serializer.save(patient=self.request.user)

    def update(self, request, *args, **kwargs):
        # Handles role-based update restrictions and status transitions
        instance = self.get_object()
        user = request.user
        new_status = request.data.get('status')

        # Patient update rules
        if user.role == "patient":
            if instance.patient != user:
                raise PermissionDenied("Unauthorized.")
            
            # Patient can only CANCEL if Pending.
            if new_status == "Cancelled":
                if instance.status != "Pending":
                    raise PermissionDenied("You can only cancel pending appointments.")
            elif new_status:
                raise PermissionDenied("You cannot change the status to " + new_status)
            
            # Prevent editing condition/date if not Pending
            if instance.status != "Pending":
                raise PermissionDenied("Approved/Completed appointments cannot be edited.")

        # Doctor update rules
        if user.role == "doctor":
            if instance.doctor != user:
                raise PermissionDenied("Unauthorized.")

            # Doctor can only APPROVE or REJECT if Pending.
            if new_status in ["Approved", "Rejected"]:
                if instance.status != "Pending":
                    raise PermissionDenied("Decision already made on this appointment.")
            
            # Doctor can only mark Completed if previously Approved
            elif new_status == "Completed":
                if instance.status != "Approved":
                    raise PermissionDenied("Only approved appointments can be marked as completed.")
                
                # Ensure they can't "Complete" an appointment that hasn't happened yet
                if instance.date_time > timezone.now():
                    raise PermissionDenied("You cannot complete an appointment before its scheduled time.")
            
            # Doctor can only CANCEL if previously Approved
            elif new_status == "Cancelled":
                if instance.status != "Approved":
                    raise PermissionDenied("Only previously approved appointments can be cancelled by the doctor.")
            
            # Doctor cannot reset an appointment to pending once a decision is made
            elif new_status == "Pending" and instance.status != "Pending":
                raise PermissionDenied("Cannot reset an appointment to pending once a decision is made.")

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        # Handles deletion rules based on status and role
        instance = self.get_object()
        user = request.user

        # Admin can delete anything
        if user.role == "admin":
            return super().destroy(request, *args, **kwargs)

        # Patients and Doctors can only delete if Rejected, Cancelled, or Completed
        if instance.status not in ["Rejected", "Cancelled", "Completed", "Expired"]:
            raise PermissionDenied("Active or Pending appointments cannot be deleted.")

        return super().destroy(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='busy-slots/(?P<doctor_id>[^/.]+)')
    def busy_slots(self, request, doctor_id=None):
        date_str = request.query_params.get('date')

        queryset = Appointment.objects.filter(
            doctor_id=doctor_id,
            status__in=['Pending', 'Approved', 'Completed'],
        )

        if date_str:
            queryset = queryset.filter(date_time__date=date_str)

        busy_times = queryset.values_list('date_time', flat=True)

        return Response(busy_times)
    
    @action(detail=True, methods=['post'])
    def complete_appointment(self, request, pk=None):
        appointment = self.get_object()
        
        # Get data from the doctor's modal
        outcome = request.data.get('outcome', 'No outcome provided.')
        notes = request.data.get('consultation_notes', 'No specific notes provided.')
        
        appointment.status = 'Completed'
        appointment.outcome = outcome
        appointment.consultation_notes = notes
        appointment.save()
        
        return Response({'status': 'appointment completed'})