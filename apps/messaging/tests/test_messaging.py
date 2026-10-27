from django.test import TestCase
from django.urls import reverse

from apps.core.testing.factories import BookingFactory, MessageFactory
from apps.messaging.models import Message
from apps.notifications.models import Notification


class MessagingTests(TestCase):
    def setUp(self):
        self.booking = BookingFactory()
        self.pme, self.carrier = self.booking.sender, self.booking.receiver

    def test_send_message_notifies_other_party(self):
        self.client.force_login(self.pme)
        r = self.client.post(reverse("messaging:send", args=[self.booking.pk]), {"body": "Bonjour, quai n°2"})
        self.assertRedirects(r, self.booking.get_absolute_url() + "#messages", fetch_redirect_response=False)
        self.assertEqual(Message.objects.get().sender, self.pme)
        n = Notification.objects.get(user=self.carrier, kind="message")
        self.assertIn("#messages", n.url)

    def test_empty_message_rejected(self):
        self.client.force_login(self.pme)
        r = self.client.post(reverse("messaging:send", args=[self.booking.pk]), {"body": "   "}, follow=True)
        self.assertEqual(Message.objects.count(), 0)
        self.assertContains(r, "Message invalide")

    def test_thread_marks_read_and_inbox_counts_unread(self):
        MessageFactory(booking=self.booking, sender=self.pme)
        self.client.force_login(self.carrier)
        r = self.client.get(reverse("messaging:inbox"))
        self.assertEqual(r.context["threads"][0].unread, 1)
        self.client.get(self.booking.get_absolute_url())
        self.assertIsNotNone(Message.objects.get().read_at)
        r = self.client.get(reverse("messaging:inbox"))
        self.assertEqual(r.context["threads"][0].unread, 0)
        self.assertIn("Message de test", str(Message.objects.get()))

    def test_message_body_escaped(self):
        MessageFactory(booking=self.booking, sender=self.pme, body="<img src=x onerror=alert(1)>")
        self.client.force_login(self.carrier)
        r = self.client.get(self.booking.get_absolute_url())
        self.assertNotContains(r, "<img src=x onerror")
