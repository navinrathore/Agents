import sys
import os
import unittest
from pydantic import BaseModel, Field

# Ensure projects/Agents is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.utils import JsonExtractor, SchemaValidator, StructuredOutputParser

class SampleReportModel(BaseModel):
    title: str
    item_count: int
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)

class TestStructuredOutputParser(unittest.TestCase):

    def test_json_extractor_raw_and_fenced(self):
        # 1. Raw JSON
        raw_json = '{"title": "Sales Analysis", "item_count": 42}'
        extracted = JsonExtractor.extract(raw_json)
        self.assertEqual(extracted["title"], "Sales Analysis")

        # 2. Markdown fenced JSON
        fenced_json = """Here is the output:
```json
{
    "title": "Q1 Report",
    "item_count": 100,
    "tags": ["sales", "q1"],
}
```
Hope this helps!"""
        extracted_fenced = JsonExtractor.extract(fenced_json)
        self.assertEqual(extracted_fenced["title"], "Q1 Report")
        self.assertEqual(extracted_fenced["item_count"], 100)

        # 3. Conversational preamble without fences
        preamble_json = 'Sure! Here is the JSON: {"title": "Conversational", "item_count": 5}'
        extracted_preamble = JsonExtractor.extract(preamble_json)
        self.assertEqual(extracted_preamble["title"], "Conversational")

    def test_pydantic_mode_validation(self):
        # Valid Pydantic parsing
        llm_text = '```json\n{"title": "Inventory Audit", "item_count": "150", "tags": ["warehouse"]}\n```'
        success, obj, err = StructuredOutputParser.parse(llm_text, response_model=SampleReportModel)
        self.assertTrue(success)
        self.assertIsInstance(obj, SampleReportModel)
        self.assertEqual(obj.title, "Inventory Audit")
        self.assertEqual(obj.item_count, 150) # Coerced string to int by Pydantic

        # Invalid Pydantic parsing (missing required field)
        invalid_llm_text = '{"tags": ["warehouse"]}'
        success, obj, err = StructuredOutputParser.parse(invalid_llm_text, response_model=SampleReportModel)
        self.assertFalse(success)
        self.assertIn("Pydantic Validation Error", err)
        self.assertIn("title", err)

    def test_raw_dict_validation_mode_without_pydantic_model(self):
        # Test Mode 2: Raw dictionary validation when response_model is None
        llm_text = '```json\n{"agent_name": "DataAnalyst", "status": "success", "loop_count": 3}\n```'
        
        # Valid required keys & expected types
        success, data, err = StructuredOutputParser.parse(
            llm_text, 
            response_model=None,
            required_keys=["agent_name", "status"],
            expected_types={"agent_name": str, "loop_count": int}
        )
        self.assertTrue(success)
        self.assertEqual(data["agent_name"], "DataAnalyst")
        self.assertEqual(data["loop_count"], 3)

        # Missing required key
        success_missing, data_missing, err_missing = StructuredOutputParser.parse(
            llm_text, 
            response_model=None,
            required_keys=["agent_name", "missing_field"]
        )
        self.assertFalse(success_missing)
        self.assertIn("Missing required JSON keys: missing_field", err_missing)

        # Mismatched expected type
        success_type, data_type, err_type = StructuredOutputParser.parse(
            llm_text, 
            response_model=None,
            expected_types={"loop_count": str}
        )
        self.assertFalse(success_type)
        self.assertIn("JSON type mismatch", err_type)

if __name__ == "__main__":
    unittest.main()
