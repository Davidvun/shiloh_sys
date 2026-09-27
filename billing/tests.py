from django.test import TestCase
from core.models import HospitalSettings, Role, User
from patients.models import Patient, Visit
from .models import Payment, PaymentType, PaymentStatus


class BillingFlowTests(TestCase):
	def setUp(self):
		self.accountant = User.objects.create_user(
			username='accountant', password='test-password', role=Role.ACCOUNTANT
		)
		self.patient = Patient.objects.create(
			full_name='Test Patient', age=30, gender='O', phone='000', address='Test address'
		)
		self.visit = Visit.objects.create(patient=self.patient, assigned_by=self.accountant)
		HospitalSettings.objects.create(pk=1, consultation_fee='75.00', currency='USD')
		self.client.force_login(self.accountant)

	def test_consultation_payment_uses_configured_fee(self):
		response = self.client.post(
			f'/billing/payments/create/{self.visit.pk}/',
			{
				'payment_type': PaymentType.CONSULTATION,
				'payment_method': 'cash',
				'total_amount': '1000',
			},
		)

		self.assertEqual(response.status_code, 302)
		payment = Payment.objects.get(visit=self.visit)
		self.assertEqual(payment.total_amount, 75)

	def test_combined_consultation_is_not_pending_and_ignores_hidden_amount(self):
		response = self.client.post(
			f'/billing/pending/visit/{self.visit.pk}/pay-all/',
			{
				'include_consultation': '1',
				'consultation_amount': '1000',
				'payment_method': 'cash',
			},
		)

		self.assertEqual(response.status_code, 302)
		payment = Payment.objects.get(visit=self.visit)
		self.assertEqual(payment.payment_type, PaymentType.COMBINED)
		self.assertEqual(payment.total_amount, 75)
		pending_response = self.client.get('/billing/pending/')
		self.assertNotContains(pending_response, self.patient.full_name)

# Create your tests here.
