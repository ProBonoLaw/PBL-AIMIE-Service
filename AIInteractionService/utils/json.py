from __future__ import annotations

import orjson
from orjson import JSONDecodeError
import re
from typing import Annotated, Any, Callable, Optional, TypeVar, Union

import jsonpatch  # type: ignore[import]
import pydantic
from pydantic import SkipValidation

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers.format_instructions import JSON_FORMAT_INSTRUCTIONS
from langchain_core.output_parsers.transform import BaseCumulativeTransformOutputParser
from langchain_core.outputs import Generation
from langchain_core.utils.json import (
    parse_partial_json,
    _parse_json
)
from langchain_core.utils.pydantic import PYDANTIC_MAJOR_VERSION

if PYDANTIC_MAJOR_VERSION < 2:
    PydanticBaseModel = pydantic.BaseModel

else:
    from pydantic.v1 import BaseModel

    # Union type needs to be last assignment to PydanticBaseModel to make mypy happy.
    PydanticBaseModel = Union[BaseModel, pydantic.BaseModel] 

TBaseModel = TypeVar("TBaseModel", bound=PydanticBaseModel) # type: ignore[valid-type]

_json_markdown_re = re.compile(r"```(json)?(.*)", re.DOTALL)

def replace_newlines_in_double_quoted_strings(input_string):
    """
    Replaces all \n characters with \\\n only within double-quoted strings in the given input string.

    Args:
        input_string (str): The input string containing double-quoted substrings.

    Returns:
        str: The modified string with \n replaced by \\\n inside double-quoted strings.
    """

    def replacer(match: re.Match):
        # Extract the content within the double quotes
        content = match.group('answer')
        # Replace unescaped \n with \\\n within the quoted content
        updated_content = content.replace("\'", "'").replace('\\n', '\n')
        json_content = orjson.dumps(updated_content)
        return f'"answer\": {json_content}, \"sources\":'

    # Pattern to match content within double quotes (excluding the quotes themselves)
    pattern = r'"answer":[\s|\n]*"(?P<answer>(.|\n)*)"[\s|\n]*(:?,)?[\s|\n]*(:?"sources":)'
    # Replace matches using the replacer function
    return re.sub(pattern, replacer, input_string, flags=re.MULTILINE)

def parse_json_markdown(
    json_string: str, *, parser: Callable[[str], Any] = parse_partial_json
) -> dict:
    """Parse a JSON string from a Markdown string.

    Args:
        json_string: The Markdown string.

    Returns:
        The parsed JSON object as a Python dictionary.
    """
    try:
        return _parse_json(json_string, parser=parser)
    except orjson.JSONDecodeError:
        # Try to find JSON string within triple backticks
        match = _json_markdown_re.search(json_string)

        # If no match found, assume the entire string is a JSON string
        # Else, use the content within the backticks
        json_str = json_string if match is None else match.group(2)
        if '’' in json_str:
            json_str = json_str.replace('’', "'")
        json_str = replace_newlines_in_double_quoted_strings(
            json_str)
    return _parse_json(json_str, parser=parser)


class JsonOutputV2Parser(BaseCumulativeTransformOutputParser[Any]):
    """Parse the output of an LLM call to a JSON object.

    When used in streaming mode, it will yield partial JSON objects containing
    all the keys that have been returned so far.

    In streaming, if `diff` is set to `True`, yields JSONPatch operations
    describing the difference between the previous and the current object.
    """

    pydantic_object: Annotated[Optional[type[TBaseModel]], SkipValidation()] = None  # type: ignore
    """The Pydantic object to use for validation.
    If None, no validation is performed."""

    def _diff(self, prev: Optional[Any], next: Any) -> Any:
        return jsonpatch.make_patch(prev, next).patch

    def _get_schema(self, pydantic_object: type[TBaseModel]) -> dict[str, Any]: # type: ignore
        if issubclass(pydantic_object, pydantic.BaseModel):
            return pydantic_object.model_json_schema()
        elif issubclass(pydantic_object, pydantic.v1.BaseModel): # type: ignore
            return pydantic_object.schema()

    def parse_result(self, result: list[Generation], *, partial: bool = False) -> Any:
        """Parse the result of an LLM call to a JSON object.

        Args:
            result: The result of the LLM call.
            partial: Whether to parse partial JSON objects.
                If True, the output will be a JSON object containing
                all the keys that have been returned so far.
                If False, the output will be the full JSON object.
                Default is False.

        Returns:
            The parsed JSON object.

        Raises:
            OutputParserException: If the output is not valid JSON.
        """
        text = result[0].text
        text = text.strip()
        if partial:
            try:
                return parse_json_markdown(text)
            except JSONDecodeError:
                return None
        else:
            try:
                return parse_json_markdown(text)
            except JSONDecodeError as e:
                msg = f"Invalid json output: {text}"
                raise OutputParserException(msg, llm_output=text) from e

    def parse(self, text: str) -> Any:
        """Parse the output of an LLM call to a JSON object.

        Args:
            text: The output of the LLM call.

        Returns:
            The parsed JSON object.
        """
        return self.parse_result([Generation(text=text)])

    def get_format_instructions(self) -> str:
        """Return the format instructions for the JSON output.

        Returns:
            The format instructions for the JSON output.
        """
        if self.pydantic_object is None:
            return "Return a JSON object."
        else:
            # Copy schema to avoid altering original Pydantic schema.
            schema = dict(self._get_schema(self.pydantic_object).items())

            # Remove extraneous fields.
            reduced_schema = schema
            if "title" in reduced_schema:
                del reduced_schema["title"]
            if "type" in reduced_schema:
                del reduced_schema["type"]
            # Ensure json in context is well-formed with double quotes.
            schema_str = orjson.dumps(reduced_schema, ensure_ascii=False)
            return JSON_FORMAT_INSTRUCTIONS.format(schema=schema_str)

    @property
    def _type(self) -> str:
        return "simple_json_output_parser"
