from celery import shared_task
from .models import Loan
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

@shared_task(bind=True, max_retries=3)
def send_loan_notification(self, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
        member_email = loan.member.user.email
        book_title = loan.book.title
        send_mail(
            subject='Book Loaned Successfully',
            message=f'Hello {loan.member.user.username},\n\nYou have successfully loaned "{book_title}".\nPlease return it by the due date.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member_email],
            fail_silently=False,
        )
    except Loan.DoesNotExist:
        pass
    except Exception as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@shared_task(bind=True, max_retries=3)
def send_overdue_email(self, title, email):
    try:
        send_mail(
            subject='Book Loan Overdue',
            message=f"Hello, your book {title}'s loan is overdue, please return back asap",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Loan.DoesNotExist:
        pass
    except Exception as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


# A functional Celery task that sends overdue notifications.
@shared_task(bind=True, max_retries=3)
def check_overdue_loans(self):
    try:
        loan_obj = Loan.objects.filter(is_returned=False, due_date__lt=timezone.now())
        # we need to send emails separately to members with their loaned books
        for loan in loan_obj:

            send_overdue_email(loan.book.title, loan.member.user.email)
    except Exception as e:

        # adding to avoid keep sending emails incase of email service is failing
        raise self.retry(exc=e, countdown=2 ** self.request.retries)