import os
import threading
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import User
from apps.core.services import run_in_background
from apps.faculty.models import FacultyProfile


class BackgroundEmailDispatchTests(TestCase):
    def test_non_render_dispatch_runs_synchronously_and_returns_result(self):
        completed = []

        def send_email():
            completed.append(True)
            return 'sent'

        with patch.dict(os.environ, {'RENDER': 'false'}):
            queued, result = run_in_background(send_email)

        self.assertFalse(queued)
        self.assertEqual(result, 'sent')
        self.assertEqual(completed, [True])

    def test_render_dispatch_returns_while_email_work_is_still_running(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def send_slow_email():
            started.set()
            release.wait(timeout=5)
            finished.set()

        with patch.dict(os.environ, {'RENDER': 'true'}):
            with self.captureOnCommitCallbacks(execute=True):
                queued, result = run_in_background(send_slow_email)
                self.assertTrue(queued)
                self.assertIsNone(result)

            self.assertTrue(started.wait(timeout=1))
            self.assertFalse(finished.is_set())
            release.set()
            self.assertTrue(finished.wait(timeout=1))

    def test_render_thread_exceptions_are_logged(self):
        finished = threading.Event()

        def fail_to_send_email():
            try:
                raise RuntimeError('SMTP unavailable')
            finally:
                finished.set()

        with self.assertLogs('apps.core.services', level='ERROR'):
            with patch.dict(os.environ, {'RENDER': 'true'}):
                with self.captureOnCommitCallbacks(execute=True):
                    queued, _ = run_in_background(fail_to_send_email)
                    self.assertTrue(queued)
                self.assertTrue(finished.wait(timeout=1))


class RenderEmailQueueResponseTests(TestCase):
    def setUp(self):
        self.head = User.objects.create_user(
            username='render-email-head', role='depthead', college='CCS',
        )
        self.faculty_user = User.objects.create_user(
            username='render-email-faculty', role='faculty', college='CCS',
            email='faculty@example.com',
        )
        self.faculty = FacultyProfile.objects.create(
            faculty_id='render-email-faculty', user=self.faculty_user, college_id='CCS',
        )
        self.client.force_login(self.head)

    def test_render_removal_queues_without_claiming_delivery(self):
        with patch.dict(os.environ, {'RENDER': 'true'}):
            with patch('apps.depthead.views.send_faculty_removed_email'):
                with self.captureOnCommitCallbacks(execute=False):
                    response = self.client.post(
                        reverse('depthead:remove_faculty', args=[self.faculty_user.pk]),
                    )

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()['email_queued'], True)
        self.assertIsNone(response.json()['email_sent'])

    def test_non_render_removal_keeps_email_sent_field(self):
        with patch.dict(os.environ, {'RENDER': 'false'}):
            with patch('apps.depthead.views.send_faculty_removed_email'):
                response = self.client.post(
                    reverse('depthead:remove_faculty', args=[self.faculty_user.pk]),
                )

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()['email_sent'], True)
        self.assertNotIn('email_queued', response.json())
