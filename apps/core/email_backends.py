"""Django email transport using Brevo's transactional HTTPS API."""

import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


logger = logging.getLogger(__name__)


class BrevoEmailError(Exception):
    """A sanitized transport or message validation failure."""


class BrevoEmailBackend(BaseEmailBackend):
    endpoint = 'https://api.brevo.com/v3/smtp/email'
    timeout = (5, 20)  # Connection and read timeouts, in seconds.

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(**kwargs)
        self.fail_silently = fail_silently

    @staticmethod
    def _address(value):
        if not isinstance(value, str) or '\r' in value or '\n' in value:
            raise BrevoEmailError('Invalid email address.')
        try:
            name, address = parseaddr(value)
        except ValueError:
            raise BrevoEmailError('Invalid email address.') from None
        if not address or '@' not in address:
            raise BrevoEmailError('Invalid email address.')
        return {'email': address, **({'name': name} if name else {})}

    def _payload(self, message):
        # Validate Django headers before bypassing its MIME serialization.
        message.message()
        if message.attachments or message.extra_headers:
            raise BrevoEmailError('Attachments and custom headers are not supported.')
        if len(message.reply_to) > 1:
            raise BrevoEmailError('Only one reply-to address is supported.')
        if message.content_subtype not in ('plain', 'html'):
            raise BrevoEmailError('Unsupported email body type.')
        payload = {
            'sender': self._address(message.from_email),
            'subject': str(message.subject),
            'htmlContent' if message.content_subtype == 'html' else 'textContent': message.body,
        }
        for field in ('to', 'cc', 'bcc'):
            addresses = getattr(message, field)
            if addresses:
                payload[field] = [self._address(address) for address in addresses]
        if message.reply_to:
            payload['replyTo'] = self._address(message.reply_to[0])
        for content, mimetype in getattr(message, 'alternatives', ()):
            if mimetype != 'text/html' or 'htmlContent' in payload:
                raise BrevoEmailError('Unsupported or duplicate email alternative.')
            payload['htmlContent'] = content
        return payload

    def _send(self, message):
        api_key = getattr(settings, 'BREVO_API_KEY', '').strip()
        if not api_key:
            raise BrevoEmailError('BREVO_API_KEY is required for the Brevo backend.')
        try:
            payload = self._payload(message)
        except BrevoEmailError:
            raise
        except (ValueError, TypeError):
            raise BrevoEmailError('Invalid email message.') from None
        try:
            # No retries: an ambiguous timeout may occur after provider acceptance.
            with requests.post(
                self.endpoint,
                headers={'api-key': api_key, 'Accept': 'application/json'},
                json=payload,
                timeout=self.timeout,
                allow_redirects=False,
            ) as response:
                if response.status_code != 201:
                    raise BrevoEmailError(
                        f'Brevo rejected the email (HTTP {response.status_code}).'
                    )
                try:
                    result = response.json()
                except ValueError:
                    raise BrevoEmailError('Invalid Brevo acceptance response.') from None
                if not isinstance(result, dict) or not result.get('messageId'):
                    raise BrevoEmailError('Brevo response omitted the message ID.')
        except requests.RequestException:
            # Do not expose request headers, response bodies, or credentials.
            raise BrevoEmailError('Brevo HTTPS connection failed or timed out.') from None

    def send_messages(self, email_messages):
        accepted = 0
        for message in email_messages or ():
            if not message.recipients():
                continue
            try:
                self._send(message)
            except BrevoEmailError as exc:
                logger.error('Brevo email failed: %s', exc)
                if not self.fail_silently:
                    raise
            else:
                accepted += 1
        return accepted
