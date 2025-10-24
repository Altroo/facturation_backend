from facturation_backend.celery_conf import app
from celery.utils.log import get_task_logger
from account.models import CustomUser
from django.core.mail import EmailMessage

logger = get_task_logger(__name__)


@app.task(bind=True, serializer='json')
def send_email(self, user_pk, email_, mail_subject, message, code, type_):
    user = CustomUser.objects.get(pk=user_pk)
    email = EmailMessage(
        mail_subject, message, to=(email_,)
    )
    email.content_subtype = "html"
    email.send(fail_silently=False)
    if type_ == 'activation_code':
        user.activation_code = code
        user.save(update_fields=['activation_code'])
    elif type_ == 'password_reset_code':
        user.password_reset_code = code
        user.save(update_fields=['password_reset_code'])


@app.task(bind=True, serializer='json')
def start_deleting_expired_codes(self, user_pk, type_):
    user = CustomUser.objects.get(pk=user_pk)
    if type_ == 'activation':
        user.activation_code = None
        user.save(update_fields=['activation_code'])
    elif type_ == 'password_reset':
        user.password_reset_code = None
        user.save(update_fields=['password_reset_code'])
