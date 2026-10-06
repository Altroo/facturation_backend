from uuid import uuid4

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from company.models import Company
from .models import LogisticsFieldReview


class LogisticsFieldReviewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(raison_sociale="Review Co", ICE="REVIEW")
        self.other_company = Company.objects.create(raison_sociale="Other Co", ICE="OTHER")
        self.editor = CustomUser.objects.create_user(email="editor@example.test", password="pass")
        self.reader = CustomUser.objects.create_user(email="reader@example.test", password="pass")
        self.outsider = CustomUser.objects.create_user(email="staff@example.test", password="pass", is_staff=True)
        for user, role in [(self.editor, "Logistique"), (self.reader, "Lecture")]:
            Membership.objects.create(user=user, company=self.company, role=Role.objects.get_or_create(name=role)[0])
        self.client = APIClient()
        self.client.force_authenticate(self.editor)
        self.url = reverse("logistique:logistique-field-review") + f"?company_id={self.company.pk}"

    def save(self, decisions):
        return self.client.patch(self.url, {"decisions": decisions}, format="json")

    def test_initial_get_does_not_create_a_review(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"decisions": {}, "proposed_fields": {}, "updated_at": None, "can_edit": True})
        self.assertFalse(LogisticsFieldReview.objects.exists())

    def test_saved_decisions_are_shared_with_another_account(self):
        decisions = {"1-1": {"choice": "Modifier", "note": "Échéance à confirmer 🧾\nLigne 2"}}
        response = self.save(decisions)
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(self.reader)
        response = self.client.get(self.url)
        self.assertEqual(response.data["decisions"], decisions)
        self.assertFalse(response.data["can_edit"])
        self.assertIsNotNone(response.data["updated_at"])
        self.assertEqual(LogisticsFieldReview.objects.get().updated_by, self.editor)

    def test_partial_changes_preserve_other_fields_and_properties(self):
        self.save({"1-1": {"choice": "Conserver", "note": "Premier"}})
        self.save({"1-2": {"note": "Second"}})
        self.save({"1-1": {"choice": "Modifier"}})
        response = self.save({"1-1": {"note": ""}})
        self.assertEqual(response.data["decisions"], {
            "1-1": {"choice": "Modifier", "note": ""},
            "1-2": {"choice": "", "note": "Second"},
        })
        self.assertEqual(self.save({"1-1": {"note": ""}}).data["decisions"], response.data["decisions"])

    def test_other_company_and_unassigned_staff_have_no_access(self):
        other_url = reverse("logistique:logistique-field-review") + f"?company_id={self.other_company.pk}"
        for method in (self.client.get, self.client.patch):
            self.assertEqual(method(other_url).status_code, 403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.save({"1-1": {"choice": "Conserver"}}).status_code, 403)

    def test_reader_cannot_save_and_anonymous_cannot_read(self):
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.save({"1-1": {"choice": "Conserver"}}).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
        self.assertFalse(LogisticsFieldReview.objects.exists())

    def test_invalid_payloads_never_overwrite_existing_data(self):
        original = {"1-0": {"choice": "Conserver", "note": "À garder"}}
        self.save(original)
        invalid = [None, [], {}, {"1-16": {"note": "unknown"}}, {"common-6": {"note": "unknown"}},
                   {"1-01": {"note": "alias"}}, {"1-1": None}, {"1-1": {}},
                   {"1-1": {"extra": "no"}}, {"1-1": {"choice": "Approve"}},
                   {"1-1": {"choice": []}}, {"1-1": {"note": 123}},
                   {"1-1": {"note": None}}, {"1-1": {"note": "x" * 2001}}]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(self.save(value).status_code, 400)
                self.assertEqual(LogisticsFieldReview.objects.get().decisions, original)
        self.assertEqual(self.client.patch(self.url, {"decisions": original, "company_id": self.other_company.pk}, format="json").status_code, 400)

    def test_all_103_fields_and_maximum_comment_length_are_accepted(self):
        counts = {"1": 16, "2": 23, "3": 27, "4": 3, "5": 6, "6": 6, "7": 9, "8": 7, "common": 6}
        decisions = {f"{stage}-{index}": {"choice": "Supprimer", "note": "é" * 2000}
                     for stage, count in counts.items() for index in range(count)}
        self.assertEqual(len(decisions), 103)
        self.assertEqual(self.save(decisions).status_code, 200)
        self.assertEqual(LogisticsFieldReview.objects.get().decisions, decisions)

    def proposals(self, changes, **extra):
        return self.client.patch(self.url, {"proposed_fields": changes, **extra}, format="json")

    def test_proposals_save_with_decisions_and_are_shared_after_reopening(self):
        key = str(uuid4())
        proposal = {"stage": "2", "name": "Mode de livraison", "description": "Choisir bateau, avion ou camion. Obligatoire."}
        response = self.proposals({key: proposal}, decisions={"1-1": {"choice": "Modifier"}})
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(self.reader)
        response = self.client.get(self.url)
        self.assertEqual(response.data["proposed_fields"], {key: proposal})
        self.assertEqual(response.data["decisions"]["1-1"]["choice"], "Modifier")
        self.assertEqual(self.proposals({key: None}).status_code, 403)

    def test_proposal_changes_and_removal_preserve_other_reviewers_work(self):
        first, second = str(uuid4()), str(uuid4())
        original = {"stage": "1", "name": "Date", "description": "Sélectionner une date"}
        self.proposals({first: original})
        self.proposals({second: {**original, "stage": "common"}})
        self.proposals({first: {"name": "Date souhaitée"}})
        result = self.proposals({first: {"description": "Date obligatoire"}})
        self.assertEqual(result.data["proposed_fields"][first], {"stage": "1", "name": "Date souhaitée", "description": "Date obligatoire"})
        result = self.proposals({first: None})
        self.assertEqual(set(result.data["proposed_fields"]), {second})
        self.assertEqual(self.proposals({first: None}).status_code, 200)
        # A stale partial edit must not recreate an incomplete deleted proposal.
        self.assertEqual(self.proposals({first: {"name": "Stale"}}).status_code, 400)
        self.assertEqual(set(self.client.get(self.url).data["proposed_fields"]), {second})

    def test_invalid_proposal_never_changes_decisions_or_proposals(self):
        key = str(uuid4())
        original = {"stage": "1", "name": "Valide", "description": ""}
        self.proposals({key: original}, decisions={"1-1": {"note": "À garder"}})
        invalid = [None, [], {}, {"bad-id": original}, {key: []}, {key: {}},
                   {key: {"name": ""}}, {key: {"name": "   "}}, {key: {"name": 123}},
                   {key: {"name": "x" * 201}}, {key: {"stage": "9"}}, {key: {"stage": []}},
                   {key: {"description": None}}, {key: {"description": "x" * 2001}},
                   {key: {"extra": "no"}}, {str(uuid4()): {"name": "Incomplete"}}]
        for value in invalid:
            with self.subTest(value=value):
                result = self.proposals(value, decisions={"1-1": {"note": "Must not replace"}})
                self.assertEqual(result.status_code, 400)
                review = LogisticsFieldReview.objects.get()
                self.assertEqual(review.proposed_fields, {key: original})
                self.assertEqual(review.decisions["1-1"]["note"], "À garder")

    def test_all_stages_allow_proposals_with_maximum_lengths(self):
        proposals = {str(uuid4()): {"stage": stage, "name": "é" * 200, "description": "é" * 2000}
                     for stage in ["1", "2", "3", "4", "5", "6", "7", "8", "common"]}
        self.assertEqual(self.proposals(proposals).status_code, 200)
        self.assertEqual(self.client.get(self.url).data["proposed_fields"], proposals)
        # The old client's decisions-only saves must leave all proposals intact.
        self.save({"1-1": {"choice": "Conserver"}})
        self.assertEqual(self.client.get(self.url).data["proposed_fields"], proposals)

    def test_proposals_cannot_be_saved_to_another_company(self):
        self.url = reverse("logistique:logistique-field-review") + f"?company_id={self.other_company.pk}"
        self.assertEqual(self.proposals({str(uuid4()): {"stage": "1", "name": "No", "description": ""}}).status_code, 403)
