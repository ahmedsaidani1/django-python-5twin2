from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CarrierProfile, CompanyProfile, Report, User
from apps.core.testing.factories import (
    AdminFactory,
    CarrierFactory,
    FreightFactory,
    PMEFactory,
    ReportFactory,
    TripFactory,
)
from apps.notifications.models import Notification

SIGNUP = {
    "username": "nouvelle_pme",
    "first_name": "Ines",
    "last_name": "Ayari",
    "email": "ines@exemple.tn",
    "phone": "+216 71 000 000",
    "password1": "UnMotDePasse!2026",
    "password2": "UnMotDePasse!2026",
    "company_name": "Ines SARL",
    "city": "Sfax",
}


class UserModelTests(TestCase):
    def test_roles_and_display_name(self):
        pme, carrier, admin = PMEFactory(), CarrierFactory(), AdminFactory()
        self.assertTrue(pme.is_pme and not pme.is_transporteur)
        self.assertTrue(carrier.is_transporteur)
        self.assertTrue(admin.is_platform_admin)
        self.assertEqual(pme.display_name, pme.company_profile.company_name)
        su = User.objects.create_superuser("root", "r@x.tn", "x", role=User.Role.PME)
        self.assertEqual(su.effective_role, "admin")
        self.assertEqual(User(username="bob").display_name, "bob")
        self.assertEqual(carrier.get_absolute_url(), reverse("accounts:carrier", args=[carrier.pk]))
        self.assertEqual(pme.get_absolute_url(), reverse("dashboard:home"))

    def test_passwords_are_hashed(self):
        u = PMEFactory()
        self.assertNotIn("Passw0rd!x", u.password)
        self.assertTrue(u.password.startswith(("md5$", "pbkdf2_", "argon2")))

    def test_groups_created_by_migration_and_synced(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), {"PME", "Transporteur", "Administrateur"})
        pme = Group.objects.get(name="PME")
        self.assertTrue(pme.permissions.filter(codename="add_freightrequest").exists())
        self.assertFalse(pme.permissions.filter(codename="add_trip").exists())
        u = PMEFactory()
        self.assertEqual(list(u.groups.values_list("name", flat=True)), ["PME"])
        u.role = User.Role.TRANSPORTEUR
        u.save()
        self.assertEqual(list(u.groups.values_list("name", flat=True)), ["Transporteur"])

    def test_profiles_and_report_str(self):
        self.assertIn("PME", str(CompanyProfile(company_name="PME X")))
        self.assertEqual(str(CarrierProfile(company_name="T")), "T")
        self.assertIn("Spam", str(ReportFactory()))


class SignupLoginTests(TestCase):
    def test_signup_pme_creates_profile_and_logs_in(self):
        r = self.client.post(reverse("accounts:signup_pme"), {**SIGNUP, "sector": "Agro"})
        self.assertRedirects(r, reverse("dashboard:home"), fetch_redirect_response=False)
        u = User.objects.get(username="nouvelle_pme")
        self.assertEqual(u.role, User.Role.PME)
        self.assertEqual(u.company_profile.company_name, "Ines SARL")
        self.assertEqual(int(self.client.session["_auth_user_id"]), u.pk)

    def test_signup_carrier(self):
        r = self.client.post(reverse("accounts:signup_carrier"), {**SIGNUP, "username": "camion", "email": "c@x.tn"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(CarrierProfile.objects.filter(user__username="camion").exists())

    def test_signup_validation_errors(self):
        PMEFactory(email="ines@exemple.tn")
        r = self.client.post(reverse("accounts:signup_pme"), {**SIGNUP, "password2": "different"})
        self.assertEqual(r.status_code, 200)
        form = r.context["form"]
        self.assertIn("email", form.errors)
        self.assertIn("password2", form.errors)
        self.assertContains(r, 'aria-describedby="id_email_error"')
        self.assertContains(r, 'aria-invalid="true"')

    def test_signup_redirects_if_logged_in(self):
        self.client.force_login(PMEFactory())
        self.assertEqual(self.client.get(reverse("accounts:signup_pme")).status_code, 302)

    def test_login_logout(self):
        u = PMEFactory(username="loggy")
        r = self.client.post(reverse("accounts:login"), {"username": "loggy", "password": "Passw0rd!x"})
        self.assertEqual(r.status_code, 302)
        r = self.client.post(reverse("accounts:logout"))
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
        _ = u

    @override_settings(AXES_FAILURE_LIMIT=3)
    def test_login_rate_limited(self):
        PMEFactory(username="victim")
        for _ in range(3):
            self.client.post(reverse("accounts:login"), {"username": "victim", "password": "wrong"})
        r = self.client.post(reverse("accounts:login"), {"username": "victim", "password": "Passw0rd!x"})
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Trop de tentatives", status_code=429)

    def test_password_reset_flow(self):
        PMEFactory(email="reset@x.tn")
        r = self.client.post(reverse("accounts:password_reset"), {"email": "reset@x.tn"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/comptes/mot-de-passe/", mail.outbox[0].body)
        for name in ("password_reset_done", "password_reset_complete"):
            self.assertEqual(self.client.get(reverse(f"accounts:{name}")).status_code, 200)
        link = [line for line in mail.outbox[0].body.splitlines() if "/mot-de-passe/" in line][0]
        path = link.split("testserver")[1]
        r = self.client.get(path, follow=True)
        self.assertTrue(r.context["validlink"])
        r = self.client.post(
            r.redirect_chain[-1][0], {"new_password1": "Nouveau!Pass2026", "new_password2": "Nouveau!Pass2026"}
        )
        self.assertRedirects(r, reverse("accounts:password_reset_complete"))


class ProfileTests(TestCase):
    def test_pme_profile_update(self):
        u = PMEFactory()
        self.client.force_login(u)
        r = self.client.get(reverse("accounts:profile"))
        self.assertContains(r, "Entreprise")
        r = self.client.post(
            reverse("accounts:profile"),
            {
                "user-first_name": "A",
                "user-last_name": "B",
                "user-email": "a@b.tn",
                "user-phone": "",
                "profile-company_name": "Nouvelle Raison",
                "profile-city": "Tunis",
                "profile-sector": "",
                "profile-address": "",
                "profile-tax_id": "",
                "profile-description": "",
            },
        )
        self.assertRedirects(r, reverse("accounts:profile"))
        u.company_profile.refresh_from_db()
        self.assertEqual(u.company_profile.company_name, "Nouvelle Raison")

    def test_carrier_profile_invalid(self):
        u = CarrierFactory()
        self.client.force_login(u)
        r = self.client.post(reverse("accounts:profile"), {"user-email": "pas-un-email", "profile-company_name": ""})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["user_form"].errors)

    def test_carrier_public_profile(self):
        c = CarrierFactory()
        TripFactory(carrier=c)
        self.client.force_login(PMEFactory())
        r = self.client.get(reverse("accounts:carrier", args=[c.pk]))
        self.assertContains(r, c.carrier_profile.company_name)
        self.assertEqual(self.client.get(reverse("accounts:carrier", args=[PMEFactory().pk])).status_code, 404)


class ReportAndModerationTests(TestCase):
    def setUp(self):
        self.admin = AdminFactory()
        self.reporter = PMEFactory()
        self.freight = FreightFactory()

    def test_report_annonce_notifies_admins(self):
        self.client.force_login(self.reporter)
        url = reverse("accounts:report", args=["annonce", self.freight.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"reason": "spam", "details": "pub"})
        self.assertRedirects(r, self.freight.get_absolute_url())
        self.assertEqual(Report.objects.get().target, self.freight)
        self.assertTrue(Notification.objects.filter(user=self.admin, kind="moderation").exists())

    def test_cannot_report_own_content_or_unknown_kind(self):
        self.client.force_login(self.freight.pme)
        self.assertEqual(
            self.client.get(reverse("accounts:report", args=["annonce", self.freight.pk])).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("accounts:report", args=["truc", 1])).status_code, 404)

    def test_report_user(self):
        carrier = CarrierFactory()
        self.client.force_login(self.reporter)
        r = self.client.post(reverse("accounts:report", args=["utilisateur", carrier.pk]), {"reason": "fraude"})
        self.assertRedirects(r, carrier.get_absolute_url(), fetch_redirect_response=False)

    def test_admin_moderation_actions(self):
        self.client.force_login(self.admin)
        report = ReportFactory(target=self.freight)
        self.freight.is_flagged = True
        self.freight.save()
        r = self.client.get(reverse("accounts:moderation"))
        self.assertContains(r, self.freight.title)
        # hide the annonce → the open report is closed, the owner is notified
        self.client.post(reverse("accounts:moderation_action", args=["annonce", self.freight.pk, "desactiver"]))
        self.freight.refresh_from_db()
        report.refresh_from_db()
        self.assertFalse(self.freight.is_active)
        self.assertEqual(report.status, Report.Status.RESOLVED)
        self.assertTrue(Notification.objects.filter(user=self.freight.pme, kind="moderation").exists())
        # validate a flagged trip
        trip = TripFactory(is_flagged=True)
        self.client.post(reverse("accounts:moderation_action", args=["trajet", trip.pk, "valider"]))
        trip.refresh_from_db()
        self.assertFalse(trip.is_flagged)
        # deactivate a user
        bad = PMEFactory()
        self.client.post(reverse("accounts:moderation_action", args=["utilisateur", bad.pk, "desactiver"]))
        bad.refresh_from_db()
        self.assertFalse(bad.is_active)
        # reject a report, unknown action
        rep2 = ReportFactory()
        self.client.post(reverse("accounts:moderation_action", args=["signalement", rep2.pk, "rejeter"]))
        rep2.refresh_from_db()
        self.assertEqual(rep2.status, Report.Status.REJECTED)
        self.assertEqual(
            self.client.post(reverse("accounts:moderation_action", args=["signalement", rep2.pk, "bof"])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("accounts:moderation_action", args=["annonce", self.freight.pk, "bof"])
            ).status_code,
            404,
        )

    def test_admin_cannot_deactivate_self(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("accounts:moderation_action", args=["utilisateur", self.admin.pk, "desactiver"]))
        self.assertEqual(r.status_code, 403)


class DjangoAdminTests(TestCase):
    def test_admin_changelists_and_actions(self):
        from django.contrib.auth import get_user_model

        root = get_user_model().objects.create_superuser("root", "root@x.tn", "x")
        self.client.force_login(root)
        FreightFactory()
        ReportFactory()
        for url in [
            "/admin/accounts/user/",
            "/admin/accounts/companyprofile/",
            "/admin/accounts/carrierprofile/",
            "/admin/accounts/report/",
            "/admin/shipments/freightrequest/",
            "/admin/trips/trip/",
            "/admin/trips/vehicle/",
            "/admin/bookings/bookingrequest/",
            "/admin/bookings/bookingstatushistory/",
            "/admin/messaging/message/",
            "/admin/reviews/review/",
            "/admin/notifications/notification/",
            "/admin/core/aijob/",
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        u = PMEFactory()
        self.client.post("/admin/accounts/user/", {"action": "deactivate_users", "_selected_action": [u.pk]})
        u.refresh_from_db()
        self.assertFalse(u.is_active)
        self.client.post("/admin/accounts/user/", {"action": "activate_users", "_selected_action": [u.pk]})
        u.refresh_from_db()
        self.assertTrue(u.is_active)
        f = FreightFactory(is_flagged=True)
        self.client.post("/admin/shipments/freightrequest/", {"action": "unflag", "_selected_action": [f.pk]})
        self.client.post("/admin/shipments/freightrequest/", {"action": "hide", "_selected_action": [f.pk]})
        f.refresh_from_db()
        self.assertFalse(f.is_flagged or f.is_active)
        t = TripFactory()
        self.client.post("/admin/trips/trip/", {"action": "hide", "_selected_action": [t.pk]})
        rep = ReportFactory()
        self.client.post("/admin/accounts/report/", {"action": "mark_resolved", "_selected_action": [rep.pk]})
        rep.refresh_from_db()
        self.assertEqual(rep.status, Report.Status.RESOLVED)
