from unittest.mock import patch

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.providers.base.constants import AuthError
from django.contrib import messages
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from requests.exceptions import Timeout

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.views import login_page, register_page


class AuthMessageTests(SimpleTestCase):
    def request(self, registering=False):
        request = RequestFactory().get('/accounts/google/login/callback/')
        request.session = {'registration_role': 'student'} if registering else {}
        request._messages = FallbackStorage(request)
        return request

    def test_only_page_specific_message_is_shown_and_queue_is_consumed(self):
        for page, view in [('login', login_page), ('register', register_page)]:
            request = self.request()
            messages.error(request, 'Relevant failure', extra_tags=f'auth_{page}')
            messages.success(request, 'You have signed out')
            messages.success(request, 'Successfully signed in as john_doe')
            messages.error(request, 'Unrelated failure')
            messages.error(request, 'Wrong page', extra_tags='auth_register' if page == 'login' else 'auth_login')
            with patch('apps.core.views.render') as render:
                view(request)
            self.assertEqual(str(render.call_args.args[2]['auth_message']), 'Relevant failure')
            self.assertTrue(request._messages.used)

    def test_success_messages_produce_no_auth_notice(self):
        request = self.request()
        messages.success(request, 'You have signed out')
        with patch('apps.core.views.render') as render:
            login_page(request)
        self.assertIsNone(render.call_args.args[2]['auth_message'])

    def test_failure_reasons_and_destinations(self):
        for registering in [False, True]:
            for error, exception, expected in [
                (AuthError.CANCELLED, None, 'cancelled or permission was not granted'),
                (AuthError.DENIED, None, 'denied authorization'),
                (AuthError.UNKNOWN, Timeout('private details'), 'could not reach Google'),
                (AuthError.UNKNOWN, ValueError('private details'), 'did not supply a specific reason'),
            ]:
                with self.subTest(registering=registering, error=error, exception=exception):
                    request = self.request(registering)
                    with self.assertRaises(ImmediateHttpResponse) as caught:
                        FacSyncSocialAdapter().on_authentication_error(request, None, error, exception)
                    page = 'register' if registering else 'login'
                    self.assertEqual(caught.exception.response.url, reverse(f'core:{page}'))
                    notice = list(get_messages(request))[0]
                    self.assertIn(expected, str(notice))
                    self.assertNotIn('private details', str(notice))
                    self.assertIn(f'auth_{page}', notice.tags.split())
                    if registering:
                        self.assertEqual(request.session['registration_role'], 'student')
