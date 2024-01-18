from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.models import EmailAddress
from django.contrib.auth import authenticate
from django.shortcuts import redirect
from django.urls import reverse

class ConsolidatingSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # Check if the social login already exists
        if sociallogin.is_existing:
            return

        # Check if the social account email matches any existing user's email
        try:
            email = sociallogin.account.extra_data['email'].lower()
            existing_email = EmailAddress.objects.get(email__iexact=email, verified=True)

            # Link the new social login to the existing user
            sociallogin.connect(request, existing_email.user)
            
            # Check if the social account is already linked
            if sociallogin.account.pk is None and existing_email.user.socialaccount_set.all().exists():
                request.session['socialaccount_sociallogin'] = sociallogin.serialize()
                redirect_url = reverse('myapp:socialaccount_verify_password')
                raise ImmediateHttpResponse(redirect(redirect_url))

        except (EmailAddress.DoesNotExist, KeyError, MultipleObjectsReturned):
            # If no matching verified email, or multiple matches, or no email provided, do nothing
            pass
