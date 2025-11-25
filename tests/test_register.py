import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, RequestFactory
from django.template.response import TemplateResponse


class TestRegisterView(TestCase):
    """Test suite for the register view function"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.factory = RequestFactory()
        self.test_data = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'password': 'securepassword123'
        }
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_get_request_returns_registration_form(self, mock_con, mock_cur):
        """Test that GET request returns the registration form template"""
        from DocumentIntelligence.views import register
        
        # Create GET request
        request = self.factory.get('/register/')
        
        # Call the view
        response = register(request)
        
        # Verify the response uses the register.html template
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'register.html')
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_post_with_valid_credentials_registers_user(self, mock_con, mock_cur):
        """Test that POST with valid credentials successfully registers user"""
        from DocumentIntelligence.views import register
        
        # Create POST request with valid data
        request = self.factory.post('/register/', self.test_data)
        
        # Mock the database cursor
        mock_cur.execute = Mock()
        mock_con.commit = Mock()
        
        # Call the view
        response = register(request)
        
        # Verify database insert was called with correct parameters
        mock_cur.execute.assert_called_once()
        args = mock_cur.execute.call_args
        
        # Check that insert query was executed
        self.assertIn('insert into user', args[0][0].lower())
        
        # Verify commit was called
        mock_con.commit.assert_called_once()
        
        # Verify success response
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'register.html')
        self.assertIn('Registration Successful', str(response.content))
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_post_with_missing_name_field(self, mock_con, mock_cur):
        """Test that POST with missing name field still processes request"""
        from DocumentIntelligence.views import register
        
        # Create POST request without name
        data = {'email': 'john@example.com', 'password': 'password123'}
        request = self.factory.post('/register/', data)
        
        mock_cur.execute = Mock()
        mock_con.commit = Mock()
        
        # Call the view
        response = register(request)
        
        # Verify the database execute was still called (name would be None)
        mock_cur.execute.assert_called_once()
        
        # The execute call should have been made with name as None
        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        
        # First parameter (name) should be None
        self.assertIsNone(params[0])
        
        # Verify the template is still rendered
        self.assertEqual(response.status_code, 200)
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_post_with_missing_email_field(self, mock_con, mock_cur):
        """Test that POST with missing email field still processes request"""
        from DocumentIntelligence.views import register
        
        # Create POST request without email
        data = {'name': 'John Doe', 'password': 'password123'}
        request = self.factory.post('/register/', data)
        
        mock_cur.execute = Mock()
        mock_con.commit = Mock()
        
        # Call the view
        response = register(request)
        
        # Verify the database execute was called
        mock_cur.execute.assert_called_once()
        
        # The execute call should have been made with email as None
        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        
        # Second parameter (email) should be None
        self.assertIsNone(params[1])
        
        # Verify the template is still rendered
        self.assertEqual(response.status_code, 200)
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_post_with_missing_password_field(self, mock_con, mock_cur):
        """Test that POST with missing password field still processes request"""
        from DocumentIntelligence.views import register
        
        # Create POST request without password
        data = {'name': 'John Doe', 'email': 'john@example.com'}
        request = self.factory.post('/register/', data)
        
        mock_cur.execute = Mock()
        mock_con.commit = Mock()
        
        # Call the view
        response = register(request)
        
        # Verify the database execute was called
        mock_cur.execute.assert_called_once()
        
        # The execute call should have been made with password as None
        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        
        # Third parameter (password) should be None
        self.assertIsNone(params[2])
        
        # Verify the template is still rendered
        self.assertEqual(response.status_code, 200)
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_database_commit_fails(self, mock_con, mock_cur):
        """Test that database commit failure is handled"""
        from DocumentIntelligence.views import register
        
        # Create POST request with valid data
        request = self.factory.post('/register/', self.test_data)
        
        # Mock the cursor and connection
        mock_cur.execute = Mock()
        
        # Make commit raise an exception
        mock_con.commit = Mock(side_effect=Exception("Database connection error"))
        
        # Call the view - it should raise an exception since there's no error handling
        with self.assertRaises(Exception) as context:
            register(request)
        
        self.assertIn("Database connection error", str(context.exception))
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_database_insert_fails(self, mock_con, mock_cur):
        """Test that database insert failure is handled"""
        from DocumentIntelligence.views import register
        
        # Create POST request with valid data
        request = self.factory.post('/register/', self.test_data)
        
        # Make execute raise an exception
        mock_cur.execute = Mock(side_effect=Exception("Database integrity error"))
        mock_con.commit = Mock()
        
        # Call the view - it should raise an exception since there's no error handling
        with self.assertRaises(Exception) as context:
            register(request)
        
        self.assertIn("Database integrity error", str(context.exception))


class TestRegisterViewResponseData(TestCase):
    """Test suite for register view response data and context"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.factory = RequestFactory()
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_registration_success_returns_correct_message(self, mock_con, mock_cur):
        """Test that successful registration returns the correct success message"""
        from DocumentIntelligence.views import register
        
        request = self.factory.post('/register/', {
            'name': 'Jane Smith',
            'email': 'jane@example.com',
            'password': 'password456'
        })
        
        mock_cur.execute = Mock()
        mock_con.commit = Mock()
        
        response = register(request)
        
        # Check for success message in response
        self.assertIn(b'Registration Successful', response.content)
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_get_request_response_context_is_empty(self, mock_con, mock_cur):
        """Test that GET request returns register template without msg context"""
        from DocumentIntelligence.views import register
        
        request = self.factory.get('/register/')
        
        response = register(request)
        
        # Verify status code
        self.assertEqual(response.status_code, 200)
        
        # Verify template used
        self.assertTemplateUsed(response, 'register.html')


class TestRegisterViewEdgeCases(TestCase):
    """Test suite for register view edge cases"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.factory = RequestFactory()
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_post_with_empty_string_values(self, mock_con, mock_cur):
        """Test POST request with empty string values"""
        from DocumentIntelligence.views import register
        
        request = self.factory.post('/register/', {
            'name': '',
            'email': '',
            'password': ''
        })
        
        mock_cur.execute = Mock()
        mock_con.commit = Mock()
        
        response = register(request)
        
        # Verify database was called
        mock_cur.execute.assert_called_once()
        
        # Verify that empty strings are passed (not None)
        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        
        self.assertEqual(params[0], '')
        self.assertEqual(params[1], '')
        self.assertEqual(params[2], '')
    
    @patch('DocumentIntelligence.views.cur')
    @patch('DocumentIntelligence.views.con')
    def test_post_with_special_characters(self, mock_con, mock_cur):
        """Test POST request with special characters in input"""
        from DocumentIntelligence.views import register
        
        special_data = {
            'name': "O'Brien & Co.",
            'email': 'test+special@example.com',
            'password': "p@$$w0rd!#%"
        }
        
        request = self.factory.post('/register/', special_data)
        
        mock_cur.execute = Mock()
        mock_con.commit = Mock()
        
        response = register(request)
        
        # Verify database was called with special characters preserved
        mock_cur.execute.assert_called_once()
        
        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        
        self.assertEqual(params[0], "O'Brien & Co.")
        self.assertEqual(params[1], 'test+special@example.com')
        self.assertEqual(params[2], "p@$$w0rd!#%")