import unittest
from unittest.mock import patch, MagicMock
import json

# FILE: AIInteractionService/test_function_app.py

import azure.functions as func

class TestFunctionApp(unittest.TestCase):

    @patch('function_app.os.getenv')
    def test_missing_configuration_settings(self, mock_getenv):
        mock_getenv.side_effect = lambda key: None if key in ['AZURE_SEARCH_ENDPOINT', 'AZURE_SEARCH_ADMIN_KEY'] else 'some_value'
        req = MagicMock(spec=func.HttpRequest)
        with self.assertRaises(ValueError):
            main(req)

    @patch('function_app.os.getenv')
    @patch('function_app.AzureSearch')
    @patch('function_app.AzureChatOpenAI')
    @patch('function_app.CosmosDBHandler')
    @patch('function_app.CosmosDBSaver')
    @patch('function_app.StateGraph')
    def test_valid_request(self, mock_state_graph, mock_cosmos_saver, mock_cosmos_handler, mock_azure_chat, mock_azure_search, mock_getenv):
        mock_getenv.side_effect = lambda key: 'some_value'
        req = MagicMock(spec=func.HttpRequest)
        req.get_json.return_value = {
            'accountId': 'test_account',
            'sessionId': 'test_session',
            'question': 'What is AI?',
            'indexPostfix': 'test_postfix',
            'isQA': True
        }
        mock_state_graph_instance = mock_state_graph.return_value
        mock_state_graph_instance.invoke.return_value = {'answer': 'AI is artificial intelligence.'}

        resp = main(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.get_body()), {'answer': 'AI is artificial intelligence.'})

    @patch('function_app.os.getenv')
    def test_invalid_request_data(self, mock_getenv):
        mock_getenv.side_effect = lambda key: 'some_value'
        req = MagicMock(spec=func.HttpRequest)
        req.get_json.return_value = {
            'accountId': 'test_account',
            'sessionId': None,
            'question': '',
            'indexPostfix': 'test_postfix',
            'isQA': True
        }

        resp = main(req)
        self.assertEqual(resp.status_code, 400)
