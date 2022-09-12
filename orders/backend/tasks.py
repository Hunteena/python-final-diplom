from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from celery import shared_task
import time


@shared_task()
def send_email_task(title, message, addressee_list,
                    sender=settings.EMAIL_HOST_USER):
    # send an e-mail to the user
    msg = EmailMultiAlternatives(title, message, sender, addressee_list)
    msg.send()
