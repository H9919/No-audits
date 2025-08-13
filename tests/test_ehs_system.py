# tests/test_ehs_system.py - FIXED VERSION with correct class imports
import unittest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to the path to import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FIXED: Import with correct class names from services.ehs_chatbot
from services.ehs_chatbot import (
    SmartEHSChatbot as EHSChatbot,  # Alias for backward compatibility
    SmartIntentClassifier as IntentClassifier,  # Alias for backward compatibility
    SmartSlotPolicy as SlotFillingPolicy  # Alias for backward compatibility
)

# Also test that the original aliases work
try:
    from services.ehs_chatbot import EHSChatbot as DirectEHSChatbot
    from services.ehs_chatbot import IntentClassifier as DirectIntentClassifier
    from services.ehs_chatbot import SlotFillingPolicy as DirectSlotFillingPolicy
    ALIASES_AVAILABLE = True
except ImportError:
    ALIASES_AVAILABLE = False

from services.incident_validator import (
    compute_completeness, validate_record, 
    REQUIRED_BY_TYPE
)

class TestIntentClassification(unittest.TestCase):
    """Test intent classification functionality"""
    
    def setUp(self):
        self.classifier = IntentClassifier()
    
    def test_incident_classification(self):
        """Test incident reporting intent detection"""
        test_cases = [
            ("I need to report a workplace injury", "incident_reporting"),
            ("Someone got hurt at work", "incident_reporting"),
            ("There was an accident", "incident_reporting"),
            ("Property damage occurred", "incident_reporting"),
            ("Chemical spill happened", "incident_reporting")
        ]
        
        for message, expected_intent in test_cases:
            with self.subTest(message=message):
                intent, confidence = self.classifier.classify_intent(message)
                self.assertEqual(intent, expected_intent)
                self.assertGreater(confidence, 0.7)
    
    def test_safety_concern_classification(self):
        """Test safety concern intent detection"""
        test_cases = [
            ("I observed unsafe working conditions", "safety_concern"),
            ("There's a potential safety hazard", "safety_concern"),
            ("I'm concerned about workplace safety", "safety_concern"),
            ("Near miss incident", "safety_concern"),
            ("Unsafe behavior noticed", "safety_concern")
        ]
        
        for message, expected_intent in test_cases:
            with self.subTest(message=message):
                intent, confidence = self.classifier.classify_intent(message)
                self.assertEqual(intent, expected_intent)
                self.assertGreater(confidence, 0.5)
    
    def test_sds_classification(self):
        """Test SDS lookup intent detection"""
        test_cases = [
            ("I need the safety data sheet for acetone", "sds_lookup"),
            ("Where can I find chemical information", "sds_lookup"),
            ("Looking for SDS documents", "sds_lookup"),
            ("Chemical safety information needed", "sds_lookup"),
            ("Find SDS for ammonia", "sds_lookup")
        ]
        
        for message, expected_intent in test_cases:
            with self.subTest(message=message):
                intent, confidence = self.classifier.classify_intent(message)
                self.assertEqual(intent, expected_intent)
                self.assertGreater(confidence, 0.5)

class TestSlotFilling(unittest.TestCase):
    """Test slot filling policies and logic"""
    
    def setUp(self):
        self.slot_policy = SlotFillingPolicy()
    
    def test_injury_slots(self):
        """Test injury incident slot requirements"""
        injury_slots = self.slot_policy.incident_slots["injury"]
        required_slots = injury_slots["required"]
        
        expected_required = ['description', 'location', 'injured_person', 'injury_type', 'body_part', 'severity']
        self.assertEqual(set(required_slots), set(expected_required))
    
    def test_environmental_slots(self):
        """Test environmental incident slot requirements"""
        env_slots = self.slot_policy.incident_slots["environmental"]
        required_slots = env_slots["required"]
        
        expected_required = ['description', 'location', 'chemical_name', 'spill_volume', 'containment']
        self.assertEqual(set(required_slots), set(expected_required))
    
    def test_slot_questions(self):
        """Test that all required slots have questions"""
        for incident_type, slots in self.slot_policy.incident_slots.items():
            for slot in slots["required"]:
                with self.subTest(incident_type=incident_type, slot=slot):
                    self.assertIn(slot, self.slot_policy.slot_questions)
                    self.assertIsInstance(self.slot_policy.slot_questions[slot], str)
                    self.assertGreater(len(self.slot_policy.slot_questions[slot]), 10)

class TestChatbotIntegration(unittest.TestCase):
    """Test full chatbot integration and workflows"""
    
    def setUp(self):
        self.chatbot = EHSChatbot()
        # Create temporary data directory
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.data_dir.mkdir(exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    @patch('services.ehs_chatbot.Path')
    def test_incident_reporting_workflow(self, mock_path):
        """Test complete incident reporting workflow"""
        # Mock the data directory
        mock_path.return_value = self.data_dir / "incidents.json"
        
        # Start incident reporting
        response1 = self.chatbot.process_message("I need to report a workplace injury")
        self.assertEqual(self.chatbot.current_mode, "incident")
        
        # Should ask for incident details
        self.assertIn("incident", response1["message"].lower())
        self.assertEqual(response1["type"], "incident_slot_filling")
        
        # Test that conversation state is maintained
        self.assertIsInstance(self.chatbot.current_context, dict)
        self.assertIsInstance(self.chatbot.slot_filling_state, dict)
    
    def test_emergency_detection(self):
        """Test emergency situation detection"""
        emergency_messages = [
            "Emergency! Someone is bleeding badly",
            "Call 911 now!",
            "Fire in the building",
            "Someone is unconscious",
            "Heart attack in progress"
        ]
        
        for message in emergency_messages:
            with self.subTest(message=message):
                response = self.chatbot.process_message(message)
                self.assertEqual(response["type"], "emergency")
                self.assertIn("911", response["message"])

class TestIncidentValidation(unittest.TestCase):
    """Test incident validation and completeness"""
    
    def test_completeness_calculation(self):
        """Test incident completeness scoring"""
        # Complete incident
        complete_incident = {
            "type": "injury",
            "answers": {
                "people": "Detailed people information here",
                "environment": "Environmental details", 
                "cost": "Cost information",
                "legal": "Legal considerations",
                "reputation": "Reputation impact"
            },
            "chatbot_data": {
                "location": "Building A",
                "responsible_person": "John Doe"
            },
            "created_ts": 1234567890
        }
        
        completeness = compute_completeness(complete_incident)
        self.assertGreater(completeness, 80)
        
        # Incomplete incident
        incomplete_incident = {
            "type": "injury",
            "answers": {
                "people": "Brief info"
            }
        }
        
        completeness = compute_completeness(incomplete_incident)
        self.assertLess(completeness, 50)
    
    def test_validation_logic(self):
        """Test incident validation logic"""
        # Valid injury incident
        valid_incident = {
            "type": "injury",
            "answers": {
                "people": "Detailed injury information provided here",
                "legal": "OSHA reportable, notification sent"
            }
        }
        
        is_valid, missing, warnings = validate_record(valid_incident)
        self.assertTrue(is_valid)
        self.assertEqual(len(missing), 0)
        
        # Invalid incident (missing required fields)
        invalid_incident = {
            "type": "injury", 
            "answers": {
                "environment": "Some info"  # Missing required people and legal
            }
        }
        
        is_valid, missing, warnings = validate_record(invalid_incident)
        self.assertFalse(is_valid)
        self.assertIn("people", missing)
        self.assertIn("legal", missing)

class TestBackwardCompatibility(unittest.TestCase):
    """Test that aliases work correctly for backward compatibility"""
    
    def test_aliases_available(self):
        """Test that the original class names are available as aliases"""
        if ALIASES_AVAILABLE:
            # Test that the direct imports work
            self.assertTrue(DirectEHSChatbot is not None)
            self.assertTrue(DirectIntentClassifier is not None)
            self.assertTrue(DirectSlotFillingPolicy is not None)
            
            # Test that they're the same classes
            self.assertIs(DirectEHSChatbot, EHSChatbot)
            self.assertIs(DirectIntentClassifier, IntentClassifier)
            self.assertIs(DirectSlotFillingPolicy, SlotFillingPolicy)
    
    def test_class_instantiation(self):
        """Test that all classes can be instantiated"""
        # Test main classes
        chatbot = EHSChatbot()
        self.assertIsInstance(chatbot, EHSChatbot)
        
        classifier = IntentClassifier()
        self.assertIsInstance(classifier, IntentClassifier)
        
        slot_policy = SlotFillingPolicy()
        self.assertIsInstance(slot_policy, SlotFillingPolicy)
        
        # Test that they have the expected methods
        self.assertTrue(hasattr(chatbot, 'process_message'))
        self.assertTrue(hasattr(classifier, 'classify_intent'))
        self.assertTrue(hasattr(slot_policy, 'incident_slots'))

class TestSDSSystem(unittest.TestCase):
    """Test SDS ingestion and search functionality"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sds_dir = Path(self.temp_dir) / "sds"
        self.sds_dir.mkdir(exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_product_name_cleaning(self):
        """Test product name cleaning and normalization"""
        from services.sds_ingest import _clean_product_name
        
        test_cases = [
            ("ACETONE SAFETY DATA SHEET VERSION 2.1", "Acetone"),
            ("Material Safety Data Sheet - Ammonia Rev 3", "Ammonia"),
            ("  Ethanol   Product   Data  Sheet  ", "Ethanol Product Data"),
            ("SDS Methanol 2023-01-15", "Methanol")
        ]
        
        for raw_name, expected_clean in test_cases:
            with self.subTest(raw_name=raw_name):
                cleaned = _clean_product_name(raw_name)
                self.assertIn(expected_clean.lower(), cleaned.lower())
    
    def test_cas_number_extraction(self):
        """Test CAS number extraction from text"""
        from services.sds_ingest import _extract_chemical_info
        
        test_text = """
        Chemical Name: Acetone
        CAS Number: 67-64-1
        Other identifiers: CAS 108-88-3 (toluene)
        """
        
        chemical_info = _extract_chemical_info(test_text)
        
        self.assertIn("67-64-1", chemical_info["cas_numbers"])
        self.assertIn("108-88-3", chemical_info["cas_numbers"])

class TestSystemIntegration(unittest.TestCase):
    """Test integration between different system components"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.data_dir.mkdir(exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_module_imports(self):
        """Test that all modules can be imported without errors"""
        # Test that we can import the main modules
        from services.ehs_chatbot import SmartEHSChatbot
        from services.incident_validator import compute_completeness
        from services.embeddings import is_sbert_available
        
        # Test that the classes exist and have basic functionality
        chatbot = SmartEHSChatbot()
        self.assertTrue(hasattr(chatbot, 'process_message'))
        
        # Test incident validator
        test_incident = {"type": "injury", "answers": {"people": "test"}}
        completeness = compute_completeness(test_incident)
        self.assertIsInstance(completeness, int)
        self.assertGreaterEqual(completeness, 0)
        self.assertLessEqual(completeness, 100)
        
        # Test embeddings availability check
        sbert_available = is_sbert_available()
        self.assertIsInstance(sbert_available, bool)

def run_all_tests():
    """Run all test suites with proper error handling"""
    # Create test suite
    test_classes = [
        TestIntentClassification,
        TestSlotFilling, 
        TestChatbotIntegration,
        TestIncidentValidation,
        TestBackwardCompatibility,
        TestSDSSystem,
        TestSystemIntegration
    ]
    
    suite = unittest.TestSuite()
    
    for test_class in test_classes:
        try:
            tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
            suite.addTests(tests)
        except Exception as e:
            print(f"WARNING: Could not load tests from {test_class.__name__}: {e}")
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    try:
        result = runner.run(suite)
        
        # Print summary
        print(f"\n{'='*50}")
        print(f"TEST RESULTS SUMMARY")
        print(f"{'='*50}")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        
        if result.testsRun > 0:
            success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
            print(f"Success rate: {success_rate:.1f}%")
        else:
            print("Success rate: No tests run")
        
        if result.failures:
            print(f"\nFAILURES:")
            for test, traceback in result.failures:
                print(f"- {test}: {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print(f"\nERRORS:")
            for test, traceback in result.errors:
                print(f"- {test}: {traceback.split('Error:')[-1].strip()}")
        
        return result.wasSuccessful()
    
    except Exception as e:
        print(f"ERROR: Test runner failed: {e}")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
