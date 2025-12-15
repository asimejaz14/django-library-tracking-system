from datetime import timedelta

from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Author, Book, Member, Loan
from .serializers import AuthorSerializer, BookSerializer, MemberSerializer, LoanSerializer
from rest_framework.decorators import action
from django.utils import timezone
from .tasks import send_loan_notification
from django.db import transaction

class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer

class BookViewSet(viewsets.ModelViewSet):

    # for optimized access of author
    queryset = Book.objects.select_related('author').all()
    serializer_class = BookSerializer

    @action(detail=True, methods=['post'])
    def loan(self, request, pk=None):

        member_id = request.data.get('member_id')
        with transaction.atomic():
            book = Book.objects.select_for_update().get(pk=pk)
            if book.available_copies < 1:
                return Response({'error': 'No available copies.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                member = Member.objects.get(id=member_id)
            except Member.DoesNotExist:
                return Response({'error': 'Member does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
            loan = Loan.objects.create(book=book, member=member)
            book.available_copies -= 1
            book.save()
            transaction.on_commit(lambda: send_loan_notification.delay(loan.id))
            return Response({'status': 'Book loaned successfully.'}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def return_book(self, request, pk=None):
        book = self.get_object()
        member_id = request.data.get('member_id')
        try:
            loan = Loan.objects.get(book=book, member__id=member_id, is_returned=False)
        except Loan.DoesNotExist:
            return Response({'error': 'Active loan does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        loan.is_returned = True
        loan.return_date = timezone.now().date()
        loan.save()
        book.available_copies += 1
        book.save()
        return Response({'status': 'Book returned successfully.'}, status=status.HTTP_200_OK)

class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer

    # @action(methods=['get'])
    # def top_active(self, request):
        # Member.objects.

class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.select_related('book', 'member', 'member__user').all()
    serializer_class = LoanSerializer

    @action(detail=True, methods=['post'])
    def extend_due_date(self, request, pk=None):
        try:
            loan_obj = Loan.objects.get(pk=pk)
        except Loan.DoesNotExist:
            return Response({'error': 'Active loan does not exist.'}, status=status.HTTP_400_BAD_REQUEST)

        if loan_obj.due_date < timezone.now().date():
            return Response({'error': 'Loan is already overdue.'}, status=status.HTTP_400_BAD_REQUEST)
        extended_due_date = request.data.get('additional_days')
        if extended_due_date < 1:
            return Response({'error': 'Additional request days must be positive integer.'}, status=status.HTTP_400_BAD_REQUEST)
        loan_obj.due_date = loan_obj.due_date + timedelta(days=extended_due_date)
        loan_obj.save()

        result = {
            'status': 'Loan extended successfully.',
            'data': loan_obj
        }
        return Response(result, status=status.HTTP_200_OK)