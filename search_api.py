"""HTTP endpoints for account tags and direct Azure AI Search queries."""

import logging

import azure.functions as func
import orjson
from azure.core.exceptions import ResourceNotFoundError

from AIInteractionService.db.account_search import (
    list_account_search_values, normalize_tags, normalize_values, search_account_records,
)
from AIInteractionService.db.search_dates import normalize_date_filter

bp = func.Blueprint()


def _response(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=orjson.dumps(body), status_code=status, mimetype="application/json",
    )


def _account_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("accountId must be a non-empty string.")
    return value.strip()


@bp.route(route="AIInteractionService/evidence/search/values", methods=["GET"])
async def account_search_values(req: func.HttpRequest) -> func.HttpResponse:
    try:
        account_id = _account_id(req.params.get("accountId"))
    except ValueError as error:
        return _response({"message": str(error)}, 400)
    try:
        return _response({"accountId": account_id, **await list_account_search_values(account_id)})
    except (FileNotFoundError, ResourceNotFoundError):
        return _response({"message": "Account or search index not found."}, 404)
    except Exception:
        logging.exception("Account search value listing failed.")
        return _response({"message": "Unable to list account search values."}, 500)


@bp.route(route="AIInteractionService/evidence/search", methods=["POST"])
async def account_search(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object.")
        account_id = _account_id(body.get("accountId"))
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string. Use * to browse by tags.")
        tags = normalize_tags(body.get("tags", []))
        filters = {}
        for field in ("who", "where"):
            if field in body:
                filters[field] = normalize_values(body[field], field)
        for field, argument in (("whenStarted", "when_started"), ("whenEnded", "when_ended")):
            if field in body:
                filters[argument] = normalize_date_filter(body[field], field)
        top, skip = body.get("top", 20), body.get("skip", 0)
        if type(top) is not int or not 1 <= top <= 1000:
            raise ValueError("top must be an integer between 1 and 1000.")
        if type(skip) is not int or not 0 <= skip <= 100000:
            raise ValueError("skip must be an integer between 0 and 100000.")
    except ValueError as error:
        return _response({"message": str(error)}, 400)
    try:
        return _response(await search_account_records(account_id, query.strip(), tags, top, skip, **filters))
    except (FileNotFoundError, ResourceNotFoundError):
        return _response({"message": "Account or search index not found."}, 404)
    except Exception:
        logging.exception("Account search failed.")
        return _response({"message": "Unable to search account records."}, 500)
