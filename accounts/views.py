from django.shortcuts import render
from asgiref.sync import sync_to_async
from allauth.socialaccount.providers import registry
from allauth.socialaccount.models import SocialApp

from django.core.cache import cache
from django.core.mail import send_mail
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse

from django.conf import settings
from django.urls import reverse
import json
import logging

from .models import CustomUser, EmailVerificationCode

logger = logging.getLogger(__name__)


def disabled(request):
    return HttpResponse("This URL is disabled", status=403)


async def social_login_view(request):
    providers = await get_available_providers()

    return await sync_to_async(render)(
        request,
        "accounts/login.html",
        {"providers": providers},
    )


@sync_to_async
def get_available_providers():
    # Check if the data is in the cache
    cached_providers = cache.get('available_providers')
    if cached_providers is not None:
        return cached_providers

    providers = []

    site_id = settings.SITE_ID

    for provider, name in registry.as_choices():
        if not SocialApp.objects.filter(
            provider=provider, sites__id__exact=site_id
        ).exists():
            continue

        login_url = reverse(f"{provider}_login")
        providers.append({"name": name, "login_url": login_url})

    cache.set('available_providers', providers, 60 * 60)  # Cache for 60 minutes

    return providers


@require_http_methods(["POST"])
def send_verification_code(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        
        if not email:
            return JsonResponse({'error': 'Email is required'}, status=400)
        
        # Create verification code
        verification_code = EmailVerificationCode.create_for_email(email)
        
        # Send email
        try:
            send_mail(
                subject='Your verification code',
                message=f'Your verification code is: {verification_code.code}\n\nThis code will expire in 10 minutes.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            
            logger.info(f"Verification code sent to {email}")
            return JsonResponse({'success': True, 'message': 'Verification code sent'})
            
        except Exception as e:
            logger.error(f"Failed to send email to {email}: {str(e)}")
            return JsonResponse({'error': 'Failed to send email'}, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in send_verification_code: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@require_http_methods(["POST"])
def verify_code(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        code = data.get('code')
        
        if not email or not code:
            return JsonResponse({'error': 'Email and code are required'}, status=400)
        
        # Find verification code
        try:
            verification_code = EmailVerificationCode.objects.get(
                email=email, 
                code=code
            )
            
            if not verification_code.is_valid():
                return JsonResponse({'error': 'Invalid or expired code'}, status=400)
            
            # Mark code as used
            verification_code.used = True
            verification_code.save()
            
            # Get or create user
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,
                    'is_active': True,
                }
            )
            
            # Log the user in
            login(request, user, backend='allauth.account.auth_backends.AuthenticationBackend')
            
            logger.info(f"User {email} logged in via email verification")
            return JsonResponse({
                'success': True, 
                'message': 'Login successful',
                'user_created': created
            })
            
        except EmailVerificationCode.DoesNotExist:
            return JsonResponse({'error': 'Invalid code'}, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in verify_code: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


def email_login_view(request):
    """Render the email login page"""
    return render(request, 'accounts/email_login.html')
