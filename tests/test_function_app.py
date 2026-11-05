import azure.functions as func
import pytest
import uuid
from uuid import uuid4
import os
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("TEXT_EMBEDDING_OPENAI_ENDPOINT", "https://example.openai.azure.com")
os.environ.setdefault("TEXT_EMBEDDING_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_VERSION", "2024-02-01")

instrumentation = ModuleType("utils.instrumentation")
instrumentation.enable_instrumentation = lambda: None
sys.modules["utils.instrumentation"] = instrumentation

from AIInteractionService.db.cosmosdb_checkpointer import CosmosDBSaver
from AIInteractionService.db.cosmosdb_handler import CosmosDBHandler
import function_app
from unittest.mock import MagicMock, patch
from pytest import MonkeyPatch

@pytest.fixture
def mock_uuid4(monkeypatch):
    with patch.object(uuid, 'uuid4') as mock:
        mock.return_value = '987654'
        monkeypatch.setattr(function_app, 'uuid4', lambda: '987654', True)
        yield mock

@pytest.fixture
def mock_azure_search_init():
    with patch('AIInteractionService.db.azuresearch.AzureSearch.__init__') as mock:
        mock.return_value = None
        mock.as_retriever.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_azure_search_as_retriever():
    with patch('AIInteractionService.db.azuresearch.AzureSearch.as_retriever') as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_init():
    with patch('function_app.init') as mock:
        embedding = MagicMock()
        mock.return_value = (embedding, 'XXX', 'YYY')
        yield mock


@pytest.fixture
def mock_create_retrieval_chain():
    with patch('langchain.chains.retrieval.create_retrieval_chain') as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_create_history_aware_retriever():
    with patch('langchain.chains.history_aware_retriever.create_history_aware_retriever') as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_cosmos_db_handler_instance(monkeypatch):
    with patch('AIInteractionService.db.cosmosdb_handler.CosmosDBHandler') as mock:
        mock_return = MagicMock()
        mock.return_value = mock_return
        monkeypatch.setattr(function_app, 'CosmosDBHandler', mock, True)
        yield mock


@pytest.fixture
def mock_cosmos_db_handler():
    with patch.object(CosmosDBHandler, '__init__') as mock:
        mock.return_value = None
        yield mock


@pytest.fixture
def mock_key():
    with patch.dict('os.environ', {'COSMOS_MESSAGE_HISTORY_ENDPOINT': 'XXX', 'AZ_COSMOS_ACCOUNT_KEY': 'YYY'}, clear=True) as mock:
        yield mock


@pytest.fixture
def mock_cosmos_db_saver():
    with patch.object(CosmosDBSaver, '__init__', new=MagicMock()) as mock:
        mock.return_value = None
        yield mock


@pytest.fixture
def mock_cosmos_db_saver_instance(monkeypatch):
    with patch('AIInteractionService.db.cosmosdb_checkpointer.CosmosDBSaver', spec=True) as mock:
        mock_return = MagicMock()
        mock.return_value = mock_return
        monkeypatch.setattr(function_app, 'CosmosDBSaver', mock, True)
        yield mock


@pytest.fixture
def mock_state_graph():
    with patch('langgraph.graph.StateGraph', spec=True) as mock:
        validate_mock = MagicMock()
        mock.validate.return_value = validate_mock
        yield mock


@pytest.fixture
def mock_compiled_state_graph():
    with patch('langgraph.graph.state.CompiledStateGraph', spec=False) as mock:
        mock_return = MagicMock()
        mock.return_value = mock_return
        validate_mock = MagicMock()
        mock_return.validate.return_value = validate_mock
        validate_mock.invoke.return_value = {'answer': 'Paris'}
        yield mock


# async def test_function_with_qa(mock_init,
#                                 mock_azure_search_init,
#                                 mock_azure_search_as_retriever,
#                                 mock_cosmos_db_handler_instance,
#                                 mock_key,
#                                 mock_cosmos_db_saver_instance,
#                                 mock_compiled_state_graph):
#     aoai_embeddings, vector_store_address, vector_store_password = mock_init.return_value
#     body = {
#         'sessionId': '1234566',
#         'question': 'What is the capital of France?',
#         'accountId': '123',
#         'maxDocCount': 10,
#         'indexPostfix': 'test',
#         'isQA': True
#     }

#     req = func.HttpRequest(method='POST', body=json.dumps(
#         body).encode("utf-8"), url='api/AIInteractionService')

#     assert req is not None
#     func_call = main.build().get_user_function()
#     resp = await func_call(req)
#     assert resp is not None
#     assert resp.status_code == 200
#     assert resp.get_body() == b'{"answer": "Paris"}'
#     assert aoai_embeddings.embed_query.call_count == 1
#     assert mock_azure_search_init.call_args.kwargs['azure_search_endpoint'] == vector_store_address
#     assert mock_azure_search_init.call_args.kwargs['azure_search_key'] == vector_store_password
#     assert mock_cosmos_db_handler_instance.call_count == 1
#     assert mock_cosmos_db_handler_instance.call_args[0][0] == mock_key['COSMOS_MESSAGE_HISTORY_ENDPOINT']
#     assert mock_cosmos_db_handler_instance.call_args[0][1] == mock_key['AZ_COSMOS_ACCOUNT_KEY']
#     assert mock_cosmos_db_handler_instance.call_args[0][2] == 'db_conversation_history'
#     assert mock_cosmos_db_handler_instance.call_args[0][3] == 'messages2'
#     assert mock_cosmos_db_saver_instance.call_count == 1
#     assert mock_cosmos_db_saver_instance.call_args[0][0] == mock_cosmos_db_handler_instance.return_value
#     assert mock_azure_search_as_retriever.call_count == 1
#     assert mock_azure_search_as_retriever.call_args.kwargs[
#         'search_type'] == 'semantic_hybrid_score_threshold'
#     assert mock_azure_search_as_retriever.call_args.kwargs['k'] == body['maxDocCount']
#     assert mock_azure_search_as_retriever.call_args.kwargs['search_kwargs'] == {
#         'score_threshold': 1.0, 'score_type': 'reranker_score'}
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_count == 1
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_args[0][0] == {
#         "input": body['question'], "question": body['question']}
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_args.kwargs == {
#         "config": {"configurable": {"thread_id": body['sessionId'], "account_id": body['accountId']}}}


# async def test_function_without_qa(mock_init,
#                                    mock_azure_search_init,
#                                    mock_azure_search_as_retriever,
#                                    mock_cosmos_db_handler_instance,
#                                    mock_key,
#                                    mock_cosmos_db_saver_instance,
#                                    mock_compiled_state_graph):
#     aoai_embeddings, vector_store_address, vector_store_password = mock_init.return_value
#     body = {
#         'sessionId': '4554332',
#         'accountId': '123',
#         'question': 'What is the capital of France?',
#         'maxDocCount': 10,
#         'indexPostfix': 'test',
#         'isQA': False
#     }

#     req = func.HttpRequest(method='POST', body=json.dumps(
#         body).encode("utf-8"), url='api/AIInteractionService')

#     assert req is not None
#     func_call = main.build().get_user_function()
#     resp = await func_call(req)
#     assert resp is not None
#     assert resp.status_code == 200
#     assert resp.get_body() == b'{"answer": "Paris"}'
#     assert aoai_embeddings.embed_query.call_count == 1
#     assert mock_azure_search_init.call_count == 1
#     assert mock_azure_search_init.call_args.kwargs['azure_search_endpoint'] == vector_store_address
#     assert mock_azure_search_init.call_args.kwargs['azure_search_key'] == vector_store_password
#     assert mock_cosmos_db_handler_instance.call_count == 1
#     assert mock_cosmos_db_handler_instance.call_args[0][0] == mock_key['COSMOS_MESSAGE_HISTORY_ENDPOINT']
#     assert mock_cosmos_db_handler_instance.call_args[0][1] == mock_key['AZ_COSMOS_ACCOUNT_KEY']
#     assert mock_cosmos_db_handler_instance.call_args[0][2] == 'db_conversation_history'
#     assert mock_cosmos_db_handler_instance.call_args[0][3] == 'messages2'
#     assert mock_cosmos_db_saver_instance.call_count == 1
#     assert mock_cosmos_db_saver_instance.call_args[0][0] == mock_cosmos_db_handler_instance.return_value
#     assert mock_azure_search_as_retriever.call_count == 1
#     assert mock_azure_search_as_retriever.call_args.kwargs['search_type'] == 'semantic_hybrid'
#     assert mock_azure_search_as_retriever.call_args.kwargs['k'] == body['maxDocCount']
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_count == 1
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_args[0][0] == {
#         "input": body['question'], "question": body['question']}
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_args.kwargs == {
#         "config": {"configurable": {"thread_id": body['sessionId'], "account_id": body['accountId']}}}


# async def test_function_missing_question(mock_init):
#     aoai_embeddings, vector_store_address, vector_store_password = mock_init.return_value
#     body = {
#         'sessionId': '4554332',
#         'accountId': '123',
#         'maxDocCount': 10,
#         'indexPostfix': 'test',
#         'isQA': False
#     }

#     req = func.HttpRequest(method='POST', body=json.dumps(
#         body).encode("utf-8"), url='api/AIInteractionService')

#     assert req is not None
#     func_call = main.build().get_user_function()
#     resp = await func_call(req)
#     assert resp is not None
#     assert resp.status_code == 400
#     assert resp.get_body() == b'{"message": "Missing question parameter"}'
#     assert aoai_embeddings.embed_query.call_count == 0


# async def test_function_app_missing_session_id(mock_uuid4,
#                                                mock_init,
#                                                mock_azure_search_init,
#                                                mock_azure_search_as_retriever,
#                                                mock_cosmos_db_handler_instance,
#                                                mock_key,
#                                                mock_cosmos_db_saver_instance,
#                                                mock_compiled_state_graph):
#     aoai_embeddings, vector_store_address, vector_store_password = mock_init.return_value
#     body = {
#         'accountId': '123',
#         'question': 'What is the capital of France?',
#         'maxDocCount': 10,
#         'indexPostfix': 'test',
#         'isQA': False
#     }

#     req = func.HttpRequest(method='POST', body=json.dumps(
#         body).encode("utf-8"), url='api/AIInteractionService')

#     assert req is not None
#     func_call = main.build().get_user_function()
#     resp = await func_call(req)
#     assert resp is not None
#     assert resp.status_code == 200
#     assert resp.get_body() == b'{"answer": "Paris"}'
#     assert aoai_embeddings.embed_query.call_count == 1
#     assert mock_azure_search_init.call_count == 1
#     assert mock_azure_search_init.call_args.kwargs['azure_search_endpoint'] == vector_store_address
#     assert mock_azure_search_init.call_args.kwargs['azure_search_key'] == vector_store_password
#     assert mock_cosmos_db_handler_instance.call_count == 1
#     assert mock_cosmos_db_handler_instance.call_args[0][0] == mock_key['COSMOS_MESSAGE_HISTORY_ENDPOINT']
#     assert mock_cosmos_db_handler_instance.call_args[0][1] == mock_key['AZ_COSMOS_ACCOUNT_KEY']
#     assert mock_cosmos_db_handler_instance.call_args[0][2] == 'db_conversation_history'
#     assert mock_cosmos_db_handler_instance.call_args[0][3] == 'messages2'
#     assert mock_cosmos_db_saver_instance.call_count == 1
#     assert mock_cosmos_db_saver_instance.call_args[0][0] == mock_cosmos_db_handler_instance.return_value
#     assert mock_azure_search_as_retriever.call_count == 1
#     assert mock_azure_search_as_retriever.call_args.kwargs['search_type'] == 'semantic_hybrid'
#     assert mock_azure_search_as_retriever.call_args.kwargs['k'] == body['maxDocCount']
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_count == 1
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_args[0][0] == {
#         "input": body['question'], "question": body['question']}
#     assert mock_compiled_state_graph.return_value.validate.return_value.invoke.call_args.kwargs == {
#         "config": {"configurable": {"thread_id": "987654", "account_id": body['accountId']}}}
