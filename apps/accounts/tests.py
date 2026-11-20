from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class DevModeSecurityTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher_word',
            password='testpassword123',
            role='teacher',
            first_name='Thầy',
            last_name='Nam'
        )
        self.student = User.objects.create_user(
            username='sv001',
            password='testpassword123',
            role='student',
            first_name='Văn An',
            last_name='Nguyễn'
        )

    @override_settings(ENABLE_DEV_SWITCHER=False)
    def test_quick_switch_blocked_when_dev_mode_disabled(self):
        """When dev mode is disabled (production), quick switch must NOT authenticate user."""
        response = self.client.get(reverse('accounts:quick_switch', args=['teacher_word']), follow=True)
        self.assertRedirects(response, reverse('accounts:login'))
        # User must NOT be authenticated
        self.assertFalse(response.context['user'].is_authenticated)
        # An error message should be displayed
        messages = list(response.context['messages'])
        self.assertTrue(any("vô hiệu hóa" in m.message for m in messages))

    @override_settings(ENABLE_DEV_SWITCHER=False)
    def test_login_page_hides_test_accounts_when_dev_mode_disabled(self):
        """When dev mode is disabled, test accounts list and dev toolbar must be hidden."""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['test_accounts']), 0)
        self.assertNotContains(response, "Kiểm thử phân quyền nhanh")
        self.assertNotContains(response, "DEV MODE")

    @override_settings(ENABLE_DEV_SWITCHER=True)
    def test_quick_switch_works_when_dev_mode_enabled(self):
        """When dev mode is enabled (development), quick switch should log user in directly."""
        response = self.client.get(reverse('accounts:quick_switch', args=['teacher_word']), follow=True)
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].username, 'teacher_word')

    def test_standard_login_succeeds(self):
        """Standard login with username and password always works regardless of dev mode."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'sv001',
            'password': 'testpassword123',
        }, follow=True)
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].username, 'sv001')
