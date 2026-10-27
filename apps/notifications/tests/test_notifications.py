from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.core.testing.factories import NotificationFactory, PMEFactory
from apps.notifications.models import Notification
from apps.notifications.services import notify


class NotificationTests(TestCase):
    def setUp(self):
        self.user = PMEFactory()
        self.client.force_login(self.user)

    def test_notify_and_failure_is_swallowed(self):
        n = notify(self.user, Notification.Kind.STATUS, "x" * 300, "/a/")
        self.assertEqual(len(n.message), 255)
        self.assertIsNone(notify(None, "status", "x"))
        with mock.patch.object(Notification.objects, "create", side_effect=RuntimeError):
            self.assertIsNone(notify(self.user, "status", "x"))
        self.assertIn(self.user.username, str(n))

    def test_badge_in_navbar_and_list(self):
        NotificationFactory(user=self.user)
        r = self.client.get(reverse("notifications:list"))
        self.assertEqual(r.context["unread_notifications_count"], 1)
        self.assertContains(r, "1 non lue")
        self.assertContains(r, 'aria-live="polite"')

    def test_open_marks_read_and_redirects_safely(self):
        n = NotificationFactory(user=self.user, url="/tableau-de-bord/")
        r = self.client.post(reverse("notifications:open", args=[n.pk]))
        self.assertRedirects(r, "/tableau-de-bord/", fetch_redirect_response=False)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        evil = NotificationFactory(user=self.user, url="https://evil.example.com/")
        r = self.client.post(reverse("notifications:open", args=[evil.pk]))
        self.assertRedirects(r, reverse("notifications:list"))

    def test_mark_all_read(self):
        NotificationFactory.create_batch(3, user=self.user)
        other = NotificationFactory()
        self.client.post(reverse("notifications:mark_all_read"))
        self.assertFalse(Notification.objects.filter(user=self.user, is_read=False).exists())
        other.refresh_from_db()
        self.assertFalse(other.is_read)
